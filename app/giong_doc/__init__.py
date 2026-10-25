"""Giọng đọc tiếng Việt tự host (VieNeu-TTS v3 Turbo, giọng "Mai Anh") cho POST /v1/tts.

Mô-đun chuẩn hóa chữ, chia mẩu và ghép âm thanh chỉ cần thư viện chuẩn và numpy, nên công cụ tạo thuyết minh tạo sẵn
(tools/thuyet-minh) nhập lại từ đây. Gói nặng (vieneu, onnxruntime, lameenc) chỉ nạp khi thật sự dùng, vì vậy
nhập gói này không cần cài gói giọng đọc.
"""
