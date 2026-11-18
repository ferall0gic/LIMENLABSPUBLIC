"""Synthetic/unit evidence only. No Rhino or Revit application is started."""
import copy
import math
import pytest
from pydantic import ValidationError
from limen_assembly_mcp.core import preview_assembly, assembly_schedule, assembly_relationships
from limen_assembly_mcp.spatial import occupancy_connectivity, access_paths, resonance_decay


def spec():
    return {"units": "mm", "assemblies": [
        {"id": "wall-1", "kind": "wall", "area_m2": 12, "layers": [
            {"material": "timber", "role": "structure", "thickness_mm": 100},
            {"material": "membrane", "role": "air_barrier", "thickness_mm": None}]},
        {"id": "roof-1", "kind": "roof", "layers": [{"material": "timber", "thickness_mm": 150}]}],
        "relationships": [{"source": "roof-1", "target": "wall-1", "kind": "supported_by"}]}


def test_preview_is_deterministic_non_mutating_and_preserves_unknown_thickness():
    data = spec(); before = copy.deepcopy(data)
    a = preview_assembly(data, "rhino"); b = preview_assembly(data, "rhino")
    assert data == before and a == b
    assert a["status"] == "plan_only" and not a["geometry_verified"]
    assert a["assemblies"][0]["total_thickness_mm"] is None
    assert a["assemblies"][0]["known_thickness_mm"] == 100
    changed = spec(); changed["assemblies"][0]["layers"][0]["thickness_mm"] = 101
    assert preview_assembly(changed, "rhino")["plan_hash"] != a["plan_hash"]
    assert preview_assembly(data, "revit")["plan_hash"] != a["plan_hash"]


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), True, "100"])
def test_thickness_must_be_positive_finite_number(bad):
    data = spec(); data["assemblies"][0]["layers"][0]["thickness_mm"] = bad
    with pytest.raises(ValidationError): preview_assembly(data, "rhino")


def test_duplicate_ids_missing_relationship_targets_and_unknown_fields_are_refused():
    data = spec(); data["assemblies"][1]["id"] = "wall-1"
    with pytest.raises(ValidationError): preview_assembly(data, "rhino")
    data = spec(); data["relationships"][0]["target"] = "missing"
    with pytest.raises(ValidationError): preview_assembly(data, "revit")
    data = spec(); data["execute_script"] = "ignored?"
    with pytest.raises(ValidationError): preview_assembly(data, "rhino")


def test_schedule_uses_area_and_mm_to_m_conversion_but_never_invents_unknown_volume():
    rows = assembly_schedule(spec())["rows"]
    assert rows[0]["volume_m3"] == pytest.approx(1.2)
    assert rows[1]["volume_m3"] is None
    assert rows[2]["area_m2"] is None and rows[2]["volume_m3"] is None
    assert assembly_relationships(spec(), "wall-1")["relationships"][0]["evidence"] == "declared"
    with pytest.raises(ValueError, match="Unknown assembly"): assembly_relationships(spec(), "missing")


def test_connectivity_uses_four_neighbours_and_does_not_call_it_architectural_order():
    result = occupancy_connectivity([[1, 0], [0, 1]])
    assert result["component_count"] == 2 and result["largest_component_cells"] == 1
    assert result["occupied_fraction"] == .5 and not result["architectural_order_verified"]
    assert occupancy_connectivity([[0, 0]])["largest_component_fraction"] == 0


def test_access_paths_handle_obstacles_and_unreachable_destinations():
    result = access_paths([[1, 1, 0], [0, 1, 0], [1, 1, 1]], [0, 0], [[2, 2], [0, 2]])
    assert [x["distance_cells"] for x in result["destinations"]] == [4, 4]
    assert result["reachable_fraction"] == 1
    assert access_paths([[1, 0, 1]], [0, 0], [[2, 0]])["destinations"][0]["distance_cells"] is None


@pytest.mark.parametrize("grid", [[], [[]], [[1], [1, 0]], [[2]], [[True]], [[float("nan")]]])
def test_grid_rejects_malformed_and_nonbinary_data(grid):
    with pytest.raises(ValueError): occupancy_connectivity(grid)


def test_access_refuses_blocked_and_out_of_bounds_points():
    for start, targets in [([1, 0], [[0, 0]]), ([3, 0], [[0, 0]]), ([0, 0], [[1, 0]]), ([0, 0], []), ([True, 0], [[0, 0]])]:
        with pytest.raises(ValueError): access_paths([[1, 0]], start, targets)


def test_decay_distinguishes_energy_from_amplitude_and_labels_analytical_evidence():
    result = resonance_decay(100, 1000, 1)
    assert result["energy_fraction"] == pytest.approx(math.exp(-2 * math.pi / 10))
    assert result["amplitude_fraction"] ** 2 == pytest.approx(result["energy_fraction"])
    assert result["evidence"] == "analytical_assumption" and not result["measured"]
    assert resonance_decay(100, 1000, 0)["energy_fraction"] == 1


@pytest.mark.parametrize("args", [(0, 1, 1), (1, 0, 1), (1, 1, -1), (float("nan"), 1, 1), (1, True, 1)])
def test_decay_rejects_invalid_inputs(args):
    with pytest.raises(ValueError): resonance_decay(*args)
