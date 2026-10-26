# HYPERLIQUID_AGENT_V1_1_LIVE_SHADOW

این پروژه بک‌تست نیست؛ Runtime زنده Shadow است.

- داده واقعی Hyperliquid Mainnet
- هیچ Order Placement ندارد
- SHADOW_MODE=true و EXECUTION_ENABLED=false اجباری
- مدل ثابت فعلی: nvidia/nemotron-3.5-lightning
- هر 5 دقیقه: Market/Stop/TP مجازی
- هر 60 دقیقه: تصمیم AI = LONG/SHORT/HOLD/CLOSE
- AI Output Hardening: JSON Schema + Pydantic contract + repair retry + provider routing
- HOLD فقط confidence=0؛ LONG/SHORT باید confidence>0 و SL/TP مثبت داشته باشند
- Risk Gate مستقل و بدون تغییر: 0.25% ریسک، 1.5% سقف ضرر روزانه، Confidence>=75، RR>=1.5
- SQLite: /data/shadow.db
- Endpoints: /health, /state, /trades, /decisions, /events, /report

برای حفظ داده روی Railway باید Volume با Mount Path /data اضافه شود.
معیار ارزیابی استراتژی: حداقل 14 روز و حداقل 30 معامله بسته‌شده؛ هرکدام دیرتر.
خطاهای Provider/Contract به عنوان تصمیم یا معامله محسوب نمی‌شوند.
