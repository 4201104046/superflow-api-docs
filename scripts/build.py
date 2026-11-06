"""Sinh <module>/openapi.json từ controller (Swagger của host) + overlay viết tay.

    python scripts/build.py reward --code-root D:/.../customapp-webapi
    python scripts/build.py reward --swagger-file swagger.json   # dùng file Swagger có sẵn, không chạy host

Luồng:
  1. Chạy host của module (dotnet run), lấy /swagger/v1/swagger.json, tắt host.
  2. Giữ các route khớp `module.include`, bỏ field server tự điền (user_id, lang_id...).
  3. Áp `fields` dùng chung trong overlays/_shared.json cho mọi property/param cùng tên.
  4. Áp overlay của module: tag, mô tả, badge, response (bọc { success, result, error }).
  5. Ghi <module>/openapi.json, cập nhật modules.json, in ra endpoint thêm/bớt so với bản trước.
"""
import argparse, copy, hashlib, json, os, re, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METHODS = ("get", "post", "put", "patch", "delete")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------- 1. Swagger từ host
def fetch_swagger_from_host(host_dir, swagger_path, timeout=240):
    env = dict(os.environ, ASPNETCORE_ENVIRONMENT="Development")
    print(f"[host] dotnet run trong {host_dir}")
    proc = subprocess.Popen(["dotnet", "run", "--no-launch-profile"], cwd=host_dir, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    try:
        base, start = None, time.time()
        for line in proc.stdout:
            m = re.search(r"Now listening on: (http://[^\s]+)", line)
            if m:
                base = m.group(1).replace("0.0.0.0", "localhost").replace("[::]", "localhost")
                break
            if time.time() - start > timeout:
                break
        if not base:
            raise RuntimeError("Host không khởi động được (không thấy 'Now listening on').")
        url = base.rstrip("/") + swagger_path
        print(f"[host] lấy {url}")
        for _ in range(30):
            try:
                with urllib.request.urlopen(url, timeout=10) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception:
                time.sleep(2)
        raise RuntimeError(f"Không lấy được {url}")
    finally:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        print("[host] đã tắt")


# ---------------------------------------------------------------- tiện ích schema
def walk_refs(node, out):
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/"):
            out.add(ref)
        for v in node.values():
            walk_refs(v, out)
    elif isinstance(node, list):
        for v in node:
            walk_refs(v, out)


def prune_components(doc):
    """Chỉ giữ component được tham chiếu (trực tiếp hoặc gián tiếp) từ paths."""
    comps = doc.get("components", {})
    keep, todo = set(), set()
    walk_refs(doc["paths"], todo)
    walk_refs({k: v for k, v in doc.items() if k not in ("paths", "components")}, todo)
    while todo:
        ref = todo.pop()
        if ref in keep:
            continue
        keep.add(ref)
        _, _, kind, name = ref.split("/", 3)
        node = comps.get(kind, {}).get(name)
        found = set()
        walk_refs(node, found)
        todo |= found - keep
    for kind in ("schemas", "parameters"):
        if kind in comps:
            comps[kind] = {n: s for n, s in comps[kind].items() if f"#/components/{kind}/{n}" in keep}


def patch_field(target, patch, override=False):
    """Gộp patch vào schema của 1 field. `$ref` thay hẳn kiểu.
    override=False: chỉ điền key code chưa có (mô tả trong /// comment thắng)."""
    if "$ref" in patch:
        nullable = target.get("nullable")
        target.clear()
        target["allOf"] = [{"$ref": patch["$ref"]}]
        if nullable:
            target["nullable"] = True
    for k, v in patch.items():
        if k != "$ref" and (override or k not in target):
            target[k] = copy.deepcopy(v)


# ---------------------------------------------------------------- 2-4. biến đổi
def build(module_id, swagger, shared, overlay):
    cfg = overlay["module"]
    include = [re.compile(p) for p in cfg["include"]]
    drop = set(shared.get("drop_params", []))
    fields = shared.get("fields", {})

    doc = {
        "openapi": swagger.get("openapi", "3.0.1"),
        "info": copy.deepcopy(overlay["info"]),
        "servers": copy.deepcopy(shared["servers"]),
        "security": [{"Bearer": []}],
        "tags": [],
        "paths": {},
        "components": {
            "securitySchemes": copy.deepcopy(shared["securitySchemes"]),
            "schemas": copy.deepcopy(swagger.get("components", {}).get("schemas", {})),
            "parameters": {},
        },
    }
    for k, v in shared.items():
        if k.startswith("x-"):
            doc[k] = copy.deepcopy(v)

    # schema dùng chung + schema response của module
    for n, sch in {**shared.get("schemas", {}), **overlay.get("schemas", {})}.items():
        doc["components"]["schemas"].setdefault(n, copy.deepcopy(sch))

    # field dùng chung: áp vào mọi property cùng tên trong mọi schema
    for name, schema in doc["components"]["schemas"].items():
        props = schema.get("properties", {})
        for p in list(props):
            if p in drop:
                del props[p]
                req = [r for r in schema.get("required", []) if r != p]
                if req:
                    schema["required"] = req
                else:
                    schema.pop("required", None)  # OpenAPI 3.0 không cho required rỗng
            elif p in fields:
                patch_field(props[p], fields[p])
    # schema patch theo tên schema (overlay module)
    for name, patch in overlay.get("schema_patches", {}).items():
        sch = doc["components"]["schemas"].get(name)
        if sch is None:
            print(f"[warn] schema_patches: không có schema {name}")
            continue
        for p, pp in patch.items():
            if p in sch.get("properties", {}):
                patch_field(sch["properties"][p], pp, override=True)

    ops_cfg = overlay.get("operations", {})
    used_tags = []
    for path, item in swagger["paths"].items():
        if not any(r.search(path) for r in include):
            continue
        for method in METHODS:
            op = item.get(method)
            if not op:
                continue
            key = f"{method.upper()} {path}"
            oc = ops_cfg.get(key, {})
            new = {}
            tag = next((t["name"] for t in overlay["tags"] if t["match"] in path), op.get("tags", ["Khác"])[0])
            new["tags"] = [tag]
            if tag not in used_tags:
                used_tags.append(tag)
            for k in ("summary", "description"):
                if oc.get(k) or op.get(k):
                    new[k] = oc.get(k) or op[k]
            if oc.get("ui"):
                new["description"] = (new.get("description", "") + "\n\n### Map lên màn hình\n\n" + oc["ui"]).strip()
            if "operationId" in oc:
                new["operationId"] = oc["operationId"]
            new.setdefault("operationId", oc.get("operationId") or re.sub(r"\W+", "_", f"{method}{path}").strip("_"))
            if oc.get("badges"):
                new["x-badges"] = [dict(shared["badges"][b]) if isinstance(b, str) else b for b in oc["badges"]]

            # query/path params: bỏ field server tự điền, param dùng chung chuyển thành $ref
            params = []
            for prm in op.get("parameters", []):
                n = prm.get("name")
                if n in drop and prm.get("in") == "query":  # field server tự điền (BaseRequestDTO); header thật thì giữ
                    continue
                if n in shared.get("parameters", {}):
                    doc["components"]["parameters"][n] = copy.deepcopy(shared["parameters"][n])
                    params.append({"$ref": f"#/components/parameters/{n}"})
                    continue
                prm = copy.deepcopy(prm)
                if n in fields:
                    patch_field(prm.setdefault("schema", {}), fields[n])
                    if "description" in fields[n]:
                        prm["description"] = fields[n]["description"]
                # vá tham số query/header của module (GET tách DTO thành param nên schema_patches không áp được)
                pp = overlay.get("param_patches", {}).get(n)
                if pp:
                    patch_field(prm.setdefault("schema", {}), pp, override=True)
                    if "description" in pp:
                        prm["description"] = pp["description"]
                params.append(prm)
            if params:
                new["parameters"] = params

            # body: chỉ giữ application/json, thêm ví dụ
            if "requestBody" in op:
                rb = copy.deepcopy(op["requestBody"])
                content = rb.get("content", {})
                rb["content"] = {"application/json": content.get("application/json") or next(iter(content.values()))}
                rb["required"] = True
                if "request_example" in oc:
                    rb["content"]["application/json"]["example"] = oc["request_example"]
                new["requestBody"] = rb

            # response: bọc { success, result, error }
            resp = {"description": "OK"}
            code_200 = op.get("responses", {}).get("200", {}).get("content", {})
            code_schema = (code_200.get("application/json") or code_200.get("text/json") or {}).get("schema")
            file_types = [ct for ct in code_200 if "json" not in ct and "text/plain" not in ct]
            if file_types and not code_schema:
                # endpoint trả file (vd Excel): giữ đúng content type, schema binary
                resp = {"description": "File tải về", "content": {ct: {"schema": {"type": "string", "format": "binary"}} for ct in file_types}}
            elif code_schema and "result" not in oc:
                resp["content"] = {"application/json": {"schema": code_schema}}
                if "result_example" in oc:
                    resp["content"]["application/json"]["example"] = {"success": True, "result": oc["result_example"], "error": None}
            elif "result" in oc:
                resp["content"] = {"application/json": {"schema": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "result": oc["result"],
                        "error": {"allOf": [{"$ref": "#/components/schemas/ErrorDTO"}], "nullable": True},
                    }}}}
                if "result_example" in oc:
                    resp["content"]["application/json"]["example"] = {
                        "success": True, "result": oc["result_example"], "error": None}
            new["responses"] = {"200": resp, "401": {"description": "Thiếu hoặc sai Bearer token"}}
            doc["paths"].setdefault(path, {})[method] = new

    missing = [k for k in ops_cfg if k.split(" ", 1)[1] not in doc["paths"]]
    for k in missing:
        print(f"[warn] overlay có {k} nhưng controller không có route này")

    doc["tags"] = [{"name": t["name"], "description": t.get("description", "")} for t in overlay["tags"] if t["name"] in used_tags]
    prune_components(doc)
    if not doc["components"]["parameters"]:
        del doc["components"]["parameters"]
    return doc


def op_keys(doc):
    return {f"{m.upper()} {p}" for p, it in doc.get("paths", {}).items() for m in it if m in METHODS}


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("module")
    ap.add_argument("--code-root", help="thư mục gốc repo code (chứa src/)")
    ap.add_argument("--swagger-file", help="dùng file swagger.json có sẵn thay vì chạy host")
    a = ap.parse_args()

    shared = load(os.path.join(ROOT, "overlays", "_shared.json"))
    overlay = load(os.path.join(ROOT, "overlays", f"{a.module}.json"))
    cfg = overlay["module"]

    if a.swagger_file:
        swagger = load(a.swagger_file)
    else:
        if not a.code_root:
            sys.exit("Cần --code-root hoặc --swagger-file")
        swagger = fetch_swagger_from_host(os.path.join(a.code_root, cfg["host_project"]), cfg.get("swagger_path", "/swagger/v1/swagger.json"))

    doc = build(a.module, swagger, shared, overlay)
    out = os.path.join(ROOT, a.module, "openapi.json")
    old = load(out) if os.path.exists(out) else {}
    dump(out, doc)

    added, removed = op_keys(doc) - op_keys(old), op_keys(old) - op_keys(doc)
    print(f"[ok] {out}: {len(op_keys(doc))} endpoint")
    for k in sorted(added):
        print(f"  + {k}")
    for k in sorted(removed):
        print(f"  - {k}")

    reg_path = os.path.join(ROOT, "modules.json")
    reg = load(reg_path) if os.path.exists(reg_path) else []
    # rev đổi theo nội dung → trình duyệt không dùng lại openapi.json cũ sau mỗi lần cập nhật
    with open(out, "rb") as f:
        rev = hashlib.sha1(f.read()).hexdigest()[:10]
    entry = {"id": a.module, "title": cfg["title"], "url": f"{a.module}/openapi.json",
             "updated": time.strftime("%H:%M %d/%m/%Y"), "rev": rev}
    reg = [e for e in reg if e["id"] != a.module] + [entry]
    reg.sort(key=lambda e: e["title"])
    dump(reg_path, reg)


if __name__ == "__main__":
    main()
