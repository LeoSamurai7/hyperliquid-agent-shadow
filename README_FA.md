# HYPERLIQUID_AGENT_V1_3_CANDIDATE_ONLY_FREE_AI

هدف این نسخه: حذف مصرف بی‌هدف AI و آماده‌سازی مستقیم برای Testnet execution.

- داده بازار: Hyperliquid Mainnet public
- Market loop: هر 5 دقیقه
- Observer پانزده‌دقیقه‌ای: خاموش و فقط تاریخچه V1.2 حفظ می‌شود
- Signal Candidate Engine: قطعی و کم‌پارامتر؛ فقط وقتی HTF و momentum هم‌جهت باشند Candidate می‌سازد
- AI: فقط روی Candidate صدا زده می‌شود، نه روی ساعت ثابت
- مدل: nvidia/nemotron-3.5-lightning:free
- OpenRouter output: Tool Calling اجباری با submit_trade_decision؛ response_format حذف شده
- Retry: صفر؛ هر Candidate فقط یک API request. خطا = fail-closed / بدون معامله
- سقف سخت AI: حداکثر 40 درخواست در روز UTC
- Risk Gate بدون تغییر: 0.25% ریسک، Confidence>=75، RR>=1.5، سقف زیان روزانه 1.5%
- Execution واقعی: هنوز در این build خاموش است
- Mainnet execution: ممنوع
- Endpoints: /health /state /trades /decisions /observer /events /report

مرحله بعد فقط V1.3 TESTNET EXECUTION VALIDATOR است. پژوهش Shadow جدید یا Observer جدید اضافه نمی‌شود.
