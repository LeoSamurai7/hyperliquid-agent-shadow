# HYPERLIQUID_AGENT_V1_2_LIVE_SHADOW

این پروژه Runtime زنده Shadow است، نه بک‌تست.

- داده واقعی Hyperliquid Mainnet
- هیچ Order Placement ندارد
- SHADOW_MODE=true و EXECUTION_ENABLED=false اجباری
- مدل: nvidia/nemotron-3.5-lightning
- هر 5 دقیقه: Market/Stop/TP مجازی
- Lane رسمی: هر 60 دقیقه تصمیم AI = LONG/SHORT/HOLD/CLOSE و تنها Lane مجاز برای معامله مجازی
- Fast Observer: هر 15 دقیقه تحلیل پژوهشی جداگانه؛ فقط hypothetical gate را ثبت می‌کند و هرگز openv/closev را صدا نمی‌زند
- AI Output Hardening: JSON Schema + Pydantic contract + repair retry + provider routing
- Risk Gate رسمی بدون تغییر: 0.25% ریسک، 1.5% سقف ضرر روزانه، Confidence>=75، RR>=1.5
- SQLite: /data/shadow.db
- Endpoints: /health, /state, /trades, /decisions, /observer, /events, /report

متغیرهای Observer به صورت پیش‌فرض:
- FAST_OBSERVER_ENABLED=true
- FAST_OBSERVER_INTERVAL_MINUTES=15
- حداقل فاصله Observer در کد 10 دقیقه قفل شده است.

Observer به هیچ عنوان جزو معاملات/تصمیم‌های رسمی Strategy شمرده نمی‌شود.
معیار ارزیابی Strategy رسمی: حداقل 14 روز و حداقل 30 معامله بسته‌شده؛ هرکدام دیرتر.
خطاهای Provider/Contract و Observer از آمار Strategy رسمی حذف می‌شوند.
Mainnet execution مجاز نیست.
