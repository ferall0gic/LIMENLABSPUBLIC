using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Autodesk.Revit.UI.Events;

namespace LimenLabs.Scratch.Revit;

// Loaded only in a separately launched Revit process carrying LIMEN_REVIT_SCRATCH_ROOT.
// No existing document is opened, saved, closed, or adopted by this add-in.
public sealed class ScratchApplication : IExternalApplication, IExternalEventHandler
{
    string? root, sessionId, documentId;
    Document? document;
    int revision;
    readonly HashSet<string> created = new();
    DateTime lastTick;
    bool attempted;
    ExternalEvent? externalEvent;
    System.Threading.Timer? timer;

    public Result OnStartup(UIControlledApplication application)
    {
        root = Environment.GetEnvironmentVariable("LIMEN_REVIT_SCRATCH_ROOT");
        if (string.IsNullOrEmpty(root)) return Result.Succeeded;
        root = Path.GetFullPath(root);
        try
        {
            var config = JsonNode.Parse(File.ReadAllText(Path.Combine(root, "scratch.json")))!;
            sessionId = config["session_id"]!.GetValue<string>();
            if (config["protocol"]!.GetValue<int>() != 1 || config["host"]!.GetValue<string>() != "revit" ||
                config["scratch_only"]!.GetValue<bool>() != true || config["scratch_document"]!.GetValue<string>() != "scratch.rvt" ||
                new DirectoryInfo(root).Name != "revit-" + Guid.ParseExact(sessionId, "N").ToString("N"))
                return Result.Failed;
            application.Idling += OnIdle;
            application.ControlledApplication.DocumentChanged += (_, e) => { if (document != null && e.GetDocument().Equals(document)) revision++; };
            externalEvent = ExternalEvent.Create(this);
            timer = new System.Threading.Timer(_ => { try { externalEvent.Raise(); } catch { } }, null, 2000, 200);
            return Result.Succeeded;
        }
        catch { return Result.Failed; }
    }

    public Result OnShutdown(UIControlledApplication application)
    {
        application.Idling -= OnIdle;
        timer?.Dispose(); externalEvent?.Dispose();
        return Result.Succeeded;
    }

    public string GetName() => "LIMEN Labs separate scratch session";
    public void Execute(UIApplication app) => OnIdle(app, null!);

    string ScratchPath => Path.Combine(root!, "scratch.rvt");
    object Binding => new { session_id = sessionId, document_id = documentId, process_id = Environment.ProcessId };
    string Revision => sessionId + ":" + revision;

    static void Atomic(string path, object value)
    {
        string temporary = path + ".tmp";
        File.WriteAllText(temporary, JsonSerializer.Serialize(value));
        File.Move(temporary, path, true);
    }

    void Guard(UIApplication app)
    {
        if (document == null || !document.IsValidObject || Path.GetFullPath(document.PathName) != ScratchPath)
            throw new InvalidOperationException("SCRATCH_DOCUMENT_CHANGED");
        if (app.ActiveUIDocument != null && !app.ActiveUIDocument.Document.Equals(document))
            throw new InvalidOperationException("ACTIVE_DOCUMENT_CHANGED");
    }

    object Context() => new { host = "revit", session_id = sessionId, document_id = documentId,
        process_id = Environment.ProcessId, scratch = true, revision = Revision,
        object_count = new FilteredElementCollector(document).OfClass(typeof(DirectShape)).GetElementCount(),
        units = "mm", evidence = "live_revit" };

    static double[] Vector(JsonNode? node, bool positive = false)
    {
        if (node is not JsonArray a || a.Count != 3) throw new InvalidOperationException("INVALID_VECTOR");
        var values = a.Select(v => v!.GetValue<double>()).ToArray();
        if (values.Any(v => !double.IsFinite(v) || Math.Abs(v) > 100000 || (positive && (v <= 0 || v > 10000))))
            throw new InvalidOperationException("INVALID_VECTOR");
        return values;
    }

    static XYZ Point(double[] mm) => new(mm[0] / 304.8, mm[1] / 304.8, mm[2] / 304.8);

    object Execute(UIApplication app, JsonNode request)
    {
        Guard(app);
        if (request["protocol"]!.GetValue<int>() != 1 || !JsonNode.DeepEquals(request["binding"], JsonSerializer.SerializeToNode(Binding)))
            throw new InvalidOperationException("BINDING_MISMATCH");
        if (request["expires_at"]!.GetValue<double>() < DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0)
            throw new InvalidOperationException("REQUEST_EXPIRED");
        string action = request["action"]!.GetValue<string>();
        var payload = request["payload"]!.AsObject();
        if (action == "context") return Context();
        if (action == "list_objects")
        {
            int limit = payload["limit"]?.GetValue<int>() ?? 50;
            if (limit < 1 || limit > 200) throw new InvalidOperationException("INVALID_LIMIT");
            var rows = new FilteredElementCollector(document).WhereElementIsNotElementType().OfClass(typeof(DirectShape)).Take(limit).Select(e =>
            {
                var box = e.get_BoundingBox(null);
                return new { id = e.UniqueId, name = e.Name, geometry_type = "DirectShape", created_by_session = created.Contains(e.UniqueId),
                    bbox_mm = box == null ? null : new { minimum = new[] { box.Min.X*304.8, box.Min.Y*304.8, box.Min.Z*304.8 },
                                                        maximum = new[] { box.Max.X*304.8, box.Max.Y*304.8, box.Max.Z*304.8 } } };
            }).ToArray();
            return new { host = "revit", revision = Revision, evidence = "live_revit", objects = rows, scratch = true };
        }
        if (action != "create_box" && action != "delete_created") throw new InvalidOperationException("UNSUPPORTED_ACTION");
        if (request["expected_revision"]?.GetValue<string>() != Revision) throw new InvalidOperationException("STALE_REVISION");
        if (action == "create_box")
        {
            if (payload.Count != 2 || !payload.ContainsKey("origin_mm") || !payload.ContainsKey("size_mm")) throw new InvalidOperationException("INVALID_BOX_PAYLOAD");
            if (created.Count >= 500) throw new InvalidOperationException("SCRATCH_OBJECT_LIMIT");
            var o = Vector(payload["origin_mm"]); var s = Vector(payload["size_mm"], true);
            var vertices = new[] { Point(o), Point(new[] {o[0]+s[0], o[1], o[2]}),
                Point(new[] {o[0]+s[0], o[1]+s[1], o[2]}), Point(new[] {o[0], o[1]+s[1], o[2]}) };
            var loop = new CurveLoop();
            for (int i = 0; i < 4; i++) loop.Append(Line.CreateBound(vertices[i], vertices[(i+1)%4]));
            var solid = GeometryCreationUtilities.CreateExtrusionGeometry(new[] { loop }, XYZ.BasisZ, s[2]/304.8);
            using var transaction = new Transaction(document, "LIMEN Labs scratch box");
            transaction.Start();
            var shape = DirectShape.CreateElement(document, new ElementId(BuiltInCategory.OST_GenericModel));
            shape.ApplicationId = "LIMEN-Labs-Scratch"; shape.ApplicationDataId = sessionId;
            shape.SetShape(new GeometryObject[] { solid });
            string id = shape.UniqueId;
            if (transaction.Commit() != TransactionStatus.Committed) throw new InvalidOperationException("CREATE_NOT_COMMITTED");
            created.Add(id); revision++;
            return new { host = "revit", revision = Revision, evidence = "live_revit", scratch = true, created_ids = new[] {id}, status = "scratch_box_created" };
        }
        if (payload.Count != 1 || payload["object_ids"] is not JsonArray ids || ids.Count != 1) throw new InvalidOperationException("DELETE_ONE_CREATED_OBJECT");
        string target = ids[0]!.GetValue<string>();
        if (!created.Contains(target)) throw new InvalidOperationException("NOT_CREATED_BY_SESSION");
        var element = document!.GetElement(target) ?? throw new InvalidOperationException("OBJECT_MISSING");
        using (var transaction = new Transaction(document, "LIMEN Labs scratch delete"))
        {
            transaction.Start(); document.Delete(element.Id);
            if (transaction.Commit() != TransactionStatus.Committed) throw new InvalidOperationException("DELETE_NOT_COMMITTED");
        }
        created.Remove(target); revision++;
        return new { host = "revit", revision = Revision, evidence = "live_revit", scratch = true, deleted_ids = new[] {target}, status = "scratch_object_deleted" };
    }

    void OnIdle(object? sender, IdlingEventArgs args)
    {
        if (sender is not UIApplication app || root == null || (DateTime.UtcNow-lastTick).TotalMilliseconds < 150) return;
        lastTick = DateTime.UtcNow;
        try
        {
            if (document == null)
            {
                if (attempted) return; attempted = true;
                if (app.ActiveUIDocument != null || File.Exists(ScratchPath)) throw new InvalidOperationException("NEW_EMPTY_INSTANCE_REQUIRED");
                document = app.Application.NewProjectDocument(UnitSystem.Metric);
                documentId = sessionId + ":" + Guid.NewGuid().ToString("N");
                document.SaveAs(ScratchPath, new SaveAsOptions { OverwriteExistingFile = false });
            }
            Atomic(Path.Combine(root, "session.json"), new { protocol = 1, host = "revit", session_id = sessionId,
                document_id = documentId, process_id = Environment.ProcessId, scratch = true,
                heartbeat = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()/1000.0, document_path = ScratchPath });
            foreach (var path in Directory.GetFiles(Path.Combine(root, "requests"), "*.json").Order().Take(1))
            {
                string id = Path.GetFileNameWithoutExtension(path);
                if (!Guid.TryParseExact(id, "N", out _)) continue;
                string claimed = Path.ChangeExtension(path, ".claimed"); File.Move(path, claimed);
                if (new FileInfo(claimed).Length > 65536) continue;
                var request = JsonNode.Parse(File.ReadAllText(claimed))!;
                if (request["request_id"]!.GetValue<string>() != id) continue;
                object response;
                try { response = new { protocol = 1, request_id = id, binding = request["binding"]!.DeepClone(), ok = true, result = Execute(app, request) }; }
                catch (Exception e) { response = new { protocol = 1, request_id = id, binding = request["binding"]!.DeepClone(), ok = false,
                    error = e is InvalidOperationException && e.Message.All(c => char.IsUpper(c) || c == '_') ? e.Message : "HOST_FAILURE: outcome requires inspection" }; }
                Atomic(Path.Combine(root, "responses", id + ".json"), response);
            }
        }
        catch (Exception e)
        {
            // Startup failure is observable; a claimed native request is never replayed.
            try { Atomic(Path.Combine(root, "host-error.json"), new { error = "HOST_FAILURE", type = e.GetType().Name }); } catch { }
        }
    }
}
