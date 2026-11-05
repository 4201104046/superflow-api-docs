// Danh sách module hiển thị ở trang chủ và dropdown chọn module.
// Thêm module mới: tạo thư mục <id>/ có index.html (+ openapi.json), rồi thêm 1 phần tử vào mảng này.
window.API_DOC_MODULES = [
  {
    id: "reward",
    name: "Reward",
    description: "Đổi quà (redemption) và lịch sử điểm (wallet transaction) cho trang chi tiết campaign.",
    base: "/api/v1/reward/web",
    endpoints: 6,
    updated: "05/11/2026"
  }
];
