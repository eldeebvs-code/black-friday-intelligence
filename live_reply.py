"""Private response to an explicit product link, freshly read on demand."""
from datetime import datetime,timezone
from live_reader import read_product,validate_url

def format_live(items,at=None):
    lines=['فحص مباشر — '+(at or datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))]
    for item in items[:3]:
        lines.append(f"{item['name']}\n{item.get('variant','')}\nالسعر: {item['price']} جنيه\nالتوفر: {'متوفر' if item['available'] else 'غير متوفر'}\nالبائع: {item.get('seller','غير معلن')}\nالضمان: {item.get('warranty','غير معلن آليًا؛ راجع صفحة الشراء')}\n{item['url']}")
    lines.append('قراءة لهذا الرابط فقط، وليست مقارنة لكل السوق. الشحن والكوبونات قد يغيران الإجمالي. لا نستنتج الأصالة أو تقييم البائع من السعر.')
    return '\n\n'.join(lines)[:4000]

def live_reply(url,browser_factory=None):
    try:store,_=validate_url(url)
    except ValueError:return 'أرسل رابط منتج مباشر من أمازون مصر أو نون مصر أو جوميا مصر أو فودافون أو أورانج. روابط الأقسام والروابط المختصرة غير مدعومة.'
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=(browser_factory or p.chromium.launch)(headless=True)
            try:items=read_product(browser,url)
            finally:browser.close()
        return format_live(items)
    except Exception:
        return f'تعذر فحص {store} مباشرة في هذه المحاولة. لن أعرض سعرًا قديمًا باعتباره سعرًا حيًا. نون وجوميا قد يرفضان الاتصال السحابي. يمكنك إعادة المحاولة لاحقًا أو إرسال رابط متجر آخر.'
