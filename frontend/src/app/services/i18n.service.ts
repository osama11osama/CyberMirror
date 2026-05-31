import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

type Locale = 'en' | 'ar';

const MESSAGES: Record<Locale, Record<string, string>> = {
  en: {
    dashboard: 'Dashboard',
    investigation: 'Investigation',
    history: 'History',
    settings: 'Settings',
    backend_connected: 'Backend connected',
    backend_offline: 'Backend offline',
    slogan: 'See Yourself as the Internet Sees You',
    platform_title: 'OSINT Self-Audit Platform',
    authorized: 'Authorized use only',
    run_scan: 'Run Full Scan',
    scanning: 'Scanning…',
    cancel_scan: 'Cancel scan',
    module_errors: 'Module errors',
    clear_cache: 'Clear cache',
    enabled_modules: 'Enabled modules',
    language: 'Language',
    risk_trend: 'Risk trend',
    select_scan: 'Select scan',
    filter_risk: 'Filter by risk',
    save_profile: 'Save profile',
  },
  ar: {
    dashboard: 'لوحة التحكم',
    investigation: 'التحقيق',
    history: 'السجل',
    settings: 'الإعدادات',
    backend_connected: 'متصل بالخادم',
    backend_offline: 'الخادم غير متصل',
    slogan: 'انظر إلى نفسك كما يراك الإنترنت',
    platform_title: 'منصة التدقيق الذاتي OSINT',
    authorized: 'استخدام مصرّح فقط',
    run_scan: 'بدء المسح الكامل',
    scanning: 'جاري المسح…',
    cancel_scan: 'إلغاء المسح',
    module_errors: 'أخطاء الوحدات',
    clear_cache: 'مسح الذاكرة المؤقتة',
    enabled_modules: 'الوحدات المفعّلة',
    language: 'اللغة',
    risk_trend: 'اتجاه المخاطر',
    select_scan: 'اختر مسحاً',
    filter_risk: 'تصفية حسب الخطر',
    save_profile: 'حفظ الملف',
  },
};

@Injectable({ providedIn: 'root' })
export class I18nService {
  private locale$ = new BehaviorSubject<Locale>(
    (localStorage.getItem('cm_locale') as Locale) || 'en'
  );

  get locale() { return this.locale$.value; }
  get isRtl() { return this.locale === 'ar'; }

  t(key: string): string {
    const loc = this.locale$.value;
    return MESSAGES[loc]?.[key] ?? MESSAGES.en[key] ?? key;
  }

  setLocale(loc: Locale) {
    localStorage.setItem('cm_locale', loc);
    this.locale$.next(loc);
    document.documentElement.lang = loc;
    document.documentElement.dir = loc === 'ar' ? 'rtl' : 'ltr';
  }

  init() {
    this.setLocale(this.locale);
  }
}
