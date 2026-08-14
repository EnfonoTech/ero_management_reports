"""AI provider registry and the single call path used by every AI feature.

Adding a provider means adding one entry to ``PROVIDERS``. The previous shape —
one pair of request functions per provider — meant a timeout or error-handling
fix had to be applied in four places and was applied in two.
"""

import time

import frappe
from frappe import _
from frappe.utils import cint

from management_reports.utils.settings import SETTINGS_DOCTYPE

ANTHROPIC = "Anthropic"
OPENAI = "OpenAI"
DEEPSEEK = "DeepSeek"

# ``style`` selects the request/response shape. DeepSeek is OpenAI-compatible, so
# it reuses that shape rather than duplicating it.
PROVIDERS = {
	ANTHROPIC: {
		"url": "https://api.anthropic.com/v1/messages",
		"key_field": "anthropic_api_key",
		"default_model": "claude-sonnet-4-20250514",
		"style": "anthropic",
	},
	OPENAI: {
		"url": "https://api.openai.com/v1/chat/completions",
		"key_field": "openai_api_key",
		"default_model": "gpt-4o",
		"style": "openai",
	},
	DEEPSEEK: {
		"url": "https://api.deepseek.com/v1/chat/completions",
		"key_field": "deepseek_api_key",
		"default_model": "deepseek-chat",
		"style": "openai",
	},
}

DEFAULT_PROVIDER = ANTHROPIC
ANALYSIS_MAX_TOKENS = 4000
CHAT_MAX_TOKENS = 2000
ANALYSIS_TIMEOUT = 90
CHAT_TIMEOUT = 60


def get_provider_config(provider: str) -> dict:
	config = PROVIDERS.get(provider)
	if not config:
		frappe.throw(_("Unknown AI provider: %s") % frappe.bold(provider or "-"), title=_("AI Provider"))

	return config


def get_provider(settings=None) -> str:
	settings = settings or get_settings()
	return settings.ai_provider or DEFAULT_PROVIDER


def get_api_key(settings, provider: str) -> str | None:
	"""Decrypted key for the selected provider.

	Keys live in Password fields, so this is the only way to read them — never
	log the return value.
	"""
	if not settings:
		return None

	return settings.get_password(get_provider_config(provider)["key_field"], raise_exception=False)


def get_model(settings, provider: str) -> str:
	"""Configured model, or the provider default if it belongs to another provider.

	One shared model Select across three providers means the stored value can be
	stale after switching provider — sending `gpt-4o` to Anthropic just errors,
	so fall back instead.
	"""
	config = get_provider_config(provider)
	model = (settings.ai_model or "").strip() if settings else ""

	if model and model in models_for(provider):
		return model

	return config["default_model"]


def models_for(provider: str) -> tuple:
	return {
		ANTHROPIC: ("claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"),
		OPENAI: ("gpt-4o", "gpt-4o-mini", "gpt-4-turbo"),
		DEEPSEEK: ("deepseek-chat", "deepseek-reasoner"),
	}.get(provider, ())


def get_settings():
	return frappe.get_cached_doc(SETTINGS_DOCTYPE)


def call_ai(
	provider: str,
	api_key: str,
	model: str,
	prompt: str | None = None,
	system_prompt: str | None = None,
	messages: list | None = None,
	max_tokens: int = ANALYSIS_MAX_TOKENS,
	timeout: int = ANALYSIS_TIMEOUT,
) -> str:
	"""Send a completion request and return the assistant's text.

	Pass either ``prompt`` for a one-shot call, or ``messages`` (plus optional
	``system_prompt``) for a conversation.
	"""
	import requests

	config = get_provider_config(provider)
	messages = messages or ([{"role": "user", "content": prompt}] if prompt else [])

	if not messages:
		frappe.throw(_("No prompt supplied to the AI provider"))

	if config["style"] == "anthropic":
		headers = {
			"x-api-key": api_key,
			"anthropic-version": "2023-06-01",
			"content-type": "application/json",
		}
		payload = {"model": model, "max_tokens": max_tokens, "messages": messages}
		if system_prompt:
			payload["system"] = system_prompt
	else:
		headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
		payload_messages = list(messages)
		if system_prompt:
			payload_messages = [{"role": "system", "content": system_prompt}, *payload_messages]
		payload = {"model": model, "max_tokens": max_tokens, "messages": payload_messages}

	response = requests.post(config["url"], headers=headers, json=payload, timeout=timeout)

	if response.status_code != 200:
		frappe.throw(_("%s API error: %s") % (provider, extract_error(response)), title=_("AI Provider"))

	return extract_text(config["style"], response.json(), provider)


def extract_error(response) -> str:
	try:
		body = response.json()
	except Exception:
		return (response.text or "")[:500]

	error = body.get("error")
	if isinstance(error, dict):
		return error.get("message") or str(error)

	return str(error or body)[:500]


def extract_text(style: str, body: dict, provider: str) -> str:
	try:
		if style == "anthropic":
			return body["content"][0]["text"]
		return body["choices"][0]["message"]["content"]
	except (KeyError, IndexError, TypeError):
		frappe.throw(_("%s returned an unexpected response shape") % provider, title=_("AI Provider"))


@frappe.whitelist()
def test_connection(provider: str | None = None) -> dict:
	"""Verify the configured key and model actually work.

	Deliberately cheap — a two-token round trip — so it can be pressed freely
	while setting a site up. Reports the real provider error rather than a
	generic failure, because "which of key / model / network is wrong" is the
	entire question being asked.
	"""
	frappe.only_for("System Manager")

	settings = get_settings()
	provider = provider or get_provider(settings)
	config = get_provider_config(provider)
	model = get_model(settings, provider)
	api_key = get_api_key(settings, provider)

	if not api_key:
		return {
			"ok": False,
			"provider": provider,
			"model": model,
			"error": _("No API key set for %s.") % provider,
		}

	started = time.monotonic()
	try:
		reply = call_ai(
			provider,
			api_key,
			model,
			prompt="Reply with the single word OK.",
			max_tokens=16,
			timeout=30,
		)
	except Exception as exc:
		frappe.clear_messages()
		frappe.log_error(frappe.get_traceback(), "Management Reports: AI connection test failed")
		return {
			"ok": False,
			"provider": provider,
			"model": model,
			"endpoint": config["url"],
			"error": str(exc),
		}

	return {
		"ok": True,
		"provider": provider,
		"model": model,
		"endpoint": config["url"],
		"latency_ms": cint((time.monotonic() - started) * 1000),
		"reply": (reply or "").strip()[:120],
	}


@frappe.whitelist()
def get_models_for_provider(provider: str) -> list:
	"""Models valid for a provider — drives the Settings model field."""
	frappe.only_for("System Manager")
	return list(models_for(provider))
