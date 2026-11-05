# superflow-api-docs

Tài liệu API cho FE, chia theo module. Deploy bằng GitHub Pages (Settings → Pages → Deploy from branch → `main` / root).

## Cấu trúc

```
index.html          trang chủ, liệt kê module từ modules.js
modules.js          danh sách module (dropdown + trang chủ đọc từ đây)
assets/docs.css     style dùng chung
assets/docs.js      dropdown chọn module, nút Copy, tô màu JSON
<module>/index.html doc của module
<module>/openapi.json  file import Apidog (Settings → Import Data → OpenAPI/Swagger)
```

## Thêm module mới

1. Tạo thư mục `<module>/` với `index.html` (copy từ `reward/index.html`, giữ `data-module="<module>"` và `data-root="../"` ở thẻ `<html>`) và `openapi.json`.
2. Thêm 1 phần tử vào `window.API_DOC_MODULES` trong `modules.js`.
