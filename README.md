# superflow-api-docs

Tài liệu API SuperFlow cho FE, chia theo module. Trang: https://ithunter.io.vn/ (GitHub Pages, giao diện [Scalar](https://github.com/scalar/scalar)).

## Cấu trúc

```
index.html               trang doc (Scalar), đọc danh sách module từ modules.json
modules.json             danh sách module (build.py tự cập nhật)
<module>/openapi.json    file sinh ra: Scalar hiển thị + import Apidog
overlays/_shared.json    khai báo dùng chung mọi module: server, auth, biến tenant_id/campaign_id..., badge, schema chung
overlays/<module>.json   riêng từng module: route nào đưa vào doc, mô tả, bảng map UI, badge, response
scripts/build.py         sinh <module>/openapi.json
CNAME                    domain ithunter.io.vn (đừng xóa)
```

## Cập nhật doc

```bash
python scripts/build.py reward --code-root D:/AZIWORLD/2.CUSTOMAPP_ACTIVATION_API/API_NEW/customapp-webapi
git add -A && git commit -m "docs(reward): ..." && git push
```

`build.py` chạy host của module (`dotnet run`), lấy `/swagger/v1/swagger.json` sinh từ controller, giữ các route khớp `module.include`,
ghép overlay rồi ghi `<module>/openapi.json`. Cuối cùng in ra endpoint thêm/bớt so với bản trước.
Không chạy được host thì dùng `--swagger-file swagger.json`.

- **Route, tham số, schema request**: lấy tự động từ controller/DTO.
- **Biến dùng chung** (`tenant_id`, `campaign_id`, `pageindex`, `sortdir`, ...): sửa 1 lần trong `overlays/_shared.json` → `fields` / `parameters`.
- **Response**: hiện viết trong overlay (`result`). Khi controller có `[ProducesResponseType(typeof(ResponseDTO<T>), 200)]` thì lấy được tự động.
- **Badge** (`Mới`, `Chưa lọc campaign`, ...): khai báo ở `_shared.json` → `badges`, gắn vào API trong overlay module.

## Thêm module

1. Tạo `overlays/<module>.json` (copy `overlays/reward.json`), sửa `module.host_project` và `module.include`.
2. Chạy `python scripts/build.py <module> --code-root ...`, commit, push.
