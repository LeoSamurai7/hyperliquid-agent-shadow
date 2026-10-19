# HYPERLIQUID_AGENT_V1_LIVE_SHADOW

این پروژه بک‌تست نیست؛ Runtime زنده Shadow است.

- داده واقعی Hyperliquid Mainnet
- هیچ Order Placement ندارد
- SHADOW_MODE=true و EXECUTION_ENABLED=false اجباری
- مدل باید `:free` باشد
- هر 5 دقیقه: Market/Stop/TP مجازی
- هر 60 دقیقه: تصمیم Qwen = LONG/SHORT/HOLD/CLOSE
- Risk Gate مستقل: 0.25% ریسک، 1.5% سقف ضرر روزانه، Confidence>=75، RR>=1.5
- SQLite: `/data/shadow.db`
- Endpoints: `/health`, `/state`, `/trades`, `/decisions`, `/report`

برای حفظ داده روی Railway باید Volume با Mount Path `/data` اضافه شود.
معیار ارزیابی: حداقل 14 روز و حداقل 30 معامله بسته‌شده؛ هرکدام دیرتر.
