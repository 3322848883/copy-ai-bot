# mailer 模块（M1 T1.3：SMTP + dev 控制台输出；模板后台可配置）
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from api.core.config import get_settings
from api.services.settings import service as settings_svc


def _wrap(tpl: str, **kwargs) -> str:
    """占位符替换渲染（用 replace 而非 str.format，避免后台模板含 CSS 花括号时抛异常）。"""
    for key, value in kwargs.items():
        tpl = tpl.replace("{" + key + "}", str(value))
    body = tpl
    return (
        '<div style="background:#0a1628;min-height:100%%;padding:32px 16px;font-family:Arial,Helvetica,sans-serif">'
        '<div style="max-width:520px;margin:auto;background:#111d35;border:1px solid #334155;'
        'border-radius:10px;padding:32px;box-sizing:border-box">'
        f"{body}"
        "</div></div>"
    )


class Mailer:
    """邮件发送：dev 环境输出到控制台，生产走 SMTP。模板后台可编辑。"""

    async def send_verify_code(self, email: str, code: str, ttl_min: int = 5) -> None:
        """发送注册验证码邮件（HTML 模板，后台可编辑）。"""
        subject, tpl = settings_svc.get_template("verify_code")
        html = _wrap(tpl, email=email, code=code, ttl=str(ttl_min))
        await self._dispatch(email, subject, html)

    async def send_subscription_expiring(self, email: str, display_name: str, expires_at: str) -> None:
        """订阅临期提醒邮件（T4 到期处理，模板后台可编辑）。"""
        subject, tpl = settings_svc.get_template("subscription_expiring")
        html = _wrap(tpl, email=email, name=display_name, expires=expires_at)
        await self._dispatch(email, subject, html)

    async def _dispatch(self, email: str, subject: str, html: str) -> None:
        """发送邮件：后台「系统设置」mail_enabled=False 时仅 dev 控制台兜底；开启则走 SMTP。"""
        settings = get_settings()
        if not settings_svc.get_rule("mail_enabled"):
            if settings.app_env == "dev":
                print(f"[MAIL-DISABLED] TO={email} SUBJECT={subject}\n{html[:200]}...")
            return
        await self._send_smtp(email, subject, html)

    async def _send_smtp(self, to: str, subject: str, html: str) -> None:
        # SMTP 参数后台可配（「系统设置→邮件」），未覆盖时沿 .env 默认值
        host = settings_svc.get_rule("smtp_host") or ""
        port = int(settings_svc.get_rule("smtp_port") or 0)
        user = settings_svc.get_rule("smtp_user") or ""
        password = settings_svc.get_rule("smtp_password") or ""
        mail_from = settings_svc.get_rule("mail_from") or ""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = mail_from
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(host, port, timeout=10) as server:
            if user:
                server.login(user, password)
            server.sendmail(mail_from, [to], msg.as_string())
