# mailer 模块（M1 T1.3：SMTP + dev 控制台输出）
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from api.core.config import get_settings

_VERIFY_CODE_HTML = """\
<html><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0a1628;padding:32px">
<div style="max-width:520px;margin:auto;background:#111d35;border:1px solid #334155;border-radius:10px;padding:32px">
<h2 style="color:#00d4aa;margin:0 0 16px">signal·saas 验证码</h2>
<p style="color:#f1f5f9;font-size:15px">您的邮箱验证码为：</p>
<div style="font-size:32px;font-weight:700;letter-spacing:8px;color:#40ffc5;background:#0a1628;border:1px dashed #00d4aa;
border-radius:8px;padding:16px;text-align:center;margin:16px 0">{code}</div>
<p style="color:#94a3b8;font-size:13px">验证码 {ttl} 分钟内有效，请勿泄露给他人。</p>
<p style="color:#64748b;font-size:11px;margin-top:24px">signal·saas 信号聚合跟单平台</p>
</div></body></html>"""

_EXPIRING_HTML = """\
<html><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0a1628;padding:32px">
<div style="max-width:520px;margin:auto;background:#111d35;border:1px solid #334155;border-radius:10px;padding:32px">
<h2 style="color:#f59e0b;margin:0 0 16px">订阅即将到期</h2>
<p style="color:#f1f5f9;font-size:15px">您好 {name}，您的订阅将于 <strong style="color:#40ffc5">{expires}</strong> 到期。</p>
<p style="color:#94a3b8;font-size:13px">到期后将暂停开仓/加仓，持仓与配置保留；续费后立即恢复。</p>
<p style="color:#64748b;font-size:11px;margin-top:24px">signal·saas 信号聚合跟单平台</p>
</div></body></html>"""


class Mailer:
    """邮件发送：dev 环境输出到控制台，生产走 SMTP。"""

    async def send_verify_code(self, email: str, code: str, ttl_min: int = 5) -> None:
        """发送注册验证码邮件（HTML 模板）。"""
        settings = get_settings()
        html = _VERIFY_CODE_HTML.format(code=code, ttl=ttl_min)
        if settings.app_env == "dev":
            # 开发：控制台输出（无 SMTP 依赖）
            print(f"[MAIL-DEV] TO={email} SUBJECT=邮箱验证码 TTL={ttl_min}min\n{html[:200]}...")
            return
        await self._send_smtp(email, "邮箱验证码", html)

    async def send_subscription_expiring(self, email: str, display_name: str, expires_at: str) -> None:
        """订阅临期提醒邮件（T4 到期处理）。"""
        settings = get_settings()
        html = _EXPIRING_HTML.format(name=display_name, expires=expires_at)
        if settings.app_env == "dev":
            print(f"[MAIL-DEV] TO={email} SUBJECT=订阅即将到期\n{html[:200]}...")
            return
        await self._send_smtp(email, "订阅即将到期", html)

    async def _send_smtp(self, to: str, subject: str, html: str) -> None:
        settings = get_settings()
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.mail_from
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password or "")
            server.sendmail(settings.mail_from, [to], msg.as_string())
