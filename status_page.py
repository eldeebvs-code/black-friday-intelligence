"""Readable repository health page; no credentials or private chat identifiers."""


def write_status(path, report, state):
    lines = ['# حالة مراقب الأسعار', '', 'آخر اكتمال فحص (UTC): ' + report['completed_at'], '',
             ('تشغيل محلي: يلزم بقاء الكمبيوتر مستيقظًا ومتصلًا بالإنترنت. انتظار 15 دقيقة بعد كل دورة.' if report.get('execution_location')=='local' else 'الجدول: كل 15 دقيقة تقريبًا؛ GitHub قد يؤخر التشغيل. الكمبيوتر لا يلزم أن يكون مفتوحًا.'), '',
             '| المصدر | الحالة | الاختيارات المفحوصة | المتوفر |', '|---|---|---:|---:|']
    for p in report['providers']:
        lines.append(f"| {p['store']} | {p['status']} | {p.get('variants', 0)} | {p.get('in_stock', 0)} |")
    lines += ['', '## نطاق التغطية', '']
    for p in report['providers']:
        lines.append('- ' + p['store'] + ': ' + p.get('scope', p.get('error', '')))
        if 'catalogue_products' in p:
            lines.append(f"  خريطة المتجر: {p['catalogue_products']} منتج، فُحصت {p['pages_checked']} صفحة في هذه الدورة؛ لا يعني فحص كل المنتجات كل 15 دقيقة.")
    lines += ['', '## مصادر غير مفعلة — لا ترسل عروضًا', '']
    lines.extend('- ' + p['store'] + ': ' + p['reason'] for p in report['inactive_sources'])
    lines += ['', '## التنبيهات', '', f"تنبيهات عروض أُرسلت في الدورة: {report['notifications_sent']}.",
              'الخصم: انخفاض 15% عن أقل سعر متوفر رُصد خلال 30 يومًا، ثم قراءة ثانية لنفس الاختيار.',
              'تقرير حالة مرة كل 24 ساعة عند التشغيل، وتنبيه تغير صحة المصادر. سكوت العروض لا يعني وجود عطل.',
              'إذا توقفت GitHub Actions نفسها فلن يستطيع هذا التقرير إرسال تنبيه؛ راجع وقت آخر تشغيل.',
              '', '[تفاصيل آخر فحص](status.json) · [التشغيلات](https://github.com/eldeebvs-code/black-friday-intelligence/actions)', '']
    path.write_text('\n'.join(lines), encoding='utf-8')
