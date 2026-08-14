import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from management_reports.utils import ai
from management_reports.utils.ai import (
	ANTHROPIC,
	DEEPSEEK,
	OPENAI,
	PROVIDERS,
	get_model,
	get_provider_config,
	models_for,
)


def settings_fields() -> dict:
	"""Shipped Management Reports Settings fields, keyed by fieldname."""
	import management_reports

	path = os.path.join(
		os.path.dirname(os.path.dirname(os.path.abspath(management_reports.__file__))),
		"management_reports",
		"management_reports",
		"doctype",
		"management_reports_settings",
		"management_reports_settings.json",
	)

	with open(path) as handle:
		schema = json.load(handle)

	return {field["fieldname"]: field for field in schema["fields"]}


class TestProviderRegistry(FrappeTestCase):
	def test_all_three_providers_registered(self):
		self.assertEqual(set(PROVIDERS), {ANTHROPIC, OPENAI, DEEPSEEK})

	def test_every_provider_is_fully_specified(self):
		for provider, config in PROVIDERS.items():
			with self.subTest(provider=provider):
				self.assertTrue(config["url"].startswith("https://"))
				self.assertTrue(config["key_field"].endswith("_api_key"))
				self.assertIn(config["style"], ("anthropic", "openai"))
				self.assertIn(config["default_model"], models_for(provider))

	def test_deepseek_uses_the_openai_request_shape(self):
		config = get_provider_config(DEEPSEEK)
		self.assertEqual(config["style"], "openai")
		self.assertEqual(config["url"], "https://api.deepseek.com/v1/chat/completions")
		self.assertEqual(config["key_field"], "deepseek_api_key")

	def test_unknown_provider_throws(self):
		self.assertRaises(frappe.ValidationError, get_provider_config, "Gemini")

	def test_every_provider_key_field_exists_on_settings(self):
		"""A key field named in the registry but missing from the DocType would
		make that provider permanently unusable.

		Read from the shipped JSON rather than synced meta, so a schema that was
		never migrated still fails the test here instead of at runtime.
		"""
		fields = settings_fields()

		for provider, config in PROVIDERS.items():
			with self.subTest(provider=provider):
				field = fields.get(config["key_field"])
				self.assertIsNotNone(field, config["key_field"] + " missing from Settings")
				self.assertEqual(field["fieldtype"], "Password")

	def test_every_provider_model_is_offered_in_settings(self):
		options = set(settings_fields()["ai_model"]["options"].split("\n"))

		for provider in PROVIDERS:
			for model in models_for(provider):
				with self.subTest(model=model):
					self.assertIn(model, options)

	def test_provider_select_lists_every_registered_provider(self):
		options = set(settings_fields()["ai_provider"]["options"].split("\n"))

		self.assertTrue(set(PROVIDERS).issubset(options))

	def test_settings_offers_no_model_that_belongs_to_no_provider(self):
		"""A leftover option would be selectable but silently fall back."""
		known = {model for provider in PROVIDERS for model in models_for(provider)}
		options = {option for option in settings_fields()["ai_model"]["options"].split("\n") if option}

		self.assertEqual(options - known, set())


class TestModelResolution(FrappeTestCase):
	def settings(self, provider, model):
		return frappe._dict({"ai_provider": provider, "ai_model": model})

	def test_matching_model_is_kept(self):
		self.assertEqual(
			get_model(self.settings(DEEPSEEK, "deepseek-reasoner"), DEEPSEEK), "deepseek-reasoner"
		)

	def test_model_from_another_provider_falls_back_to_the_default(self):
		"""Switching provider leaves a stale model in a shared Select — sending
		gpt-4o to Anthropic would just error."""
		self.assertEqual(get_model(self.settings(ANTHROPIC, "gpt-4o"), ANTHROPIC), "claude-sonnet-4-20250514")
		self.assertEqual(get_model(self.settings(DEEPSEEK, "gpt-4o"), DEEPSEEK), "deepseek-chat")

	def test_blank_model_falls_back(self):
		self.assertEqual(get_model(self.settings(OPENAI, ""), OPENAI), "gpt-4o")
		self.assertEqual(get_model(None, OPENAI), "gpt-4o")


class TestPayloadShape(FrappeTestCase):
	"""call_ai builds the request; these assert the shape without any network."""

	def setUp(self):
		self.captured = {}
		self.original_post = None

	def stub_requests(self, status=200, body=None):
		import requests

		self.original_post = requests.post

		def fake_post(url, headers=None, json=None, timeout=None):
			self.captured = {"url": url, "headers": headers, "json": json, "timeout": timeout}
			return frappe._dict(
				{
					"status_code": status,
					"json": lambda: body or {},
					"text": "stub",
				}
			)

		requests.post = fake_post

	def tearDown(self):
		if self.original_post:
			import requests

			requests.post = self.original_post

	def test_anthropic_shape(self):
		self.stub_requests(body={"content": [{"text": "hello"}]})
		reply = ai.call_ai(ANTHROPIC, "key-a", "claude-sonnet-4-20250514", prompt="hi")

		self.assertEqual(reply, "hello")
		self.assertEqual(self.captured["headers"]["x-api-key"], "key-a")
		self.assertIn("anthropic-version", self.captured["headers"])
		self.assertEqual(self.captured["json"]["messages"], [{"role": "user", "content": "hi"}])

	def test_deepseek_shape_uses_bearer_and_choices(self):
		self.stub_requests(body={"choices": [{"message": {"content": "ok"}}]})
		reply = ai.call_ai(DEEPSEEK, "key-d", "deepseek-chat", prompt="hi")

		self.assertEqual(reply, "ok")
		self.assertEqual(self.captured["headers"]["Authorization"], "Bearer key-d")
		self.assertEqual(self.captured["url"], PROVIDERS[DEEPSEEK]["url"])

	def test_system_prompt_becomes_a_message_for_openai_style(self):
		self.stub_requests(body={"choices": [{"message": {"content": "ok"}}]})
		ai.call_ai(
			DEEPSEEK,
			"key-d",
			"deepseek-chat",
			system_prompt="be terse",
			messages=[{"role": "user", "content": "hi"}],
		)

		self.assertEqual(self.captured["json"]["messages"][0], {"role": "system", "content": "be terse"})

	def test_system_prompt_is_a_top_level_field_for_anthropic(self):
		self.stub_requests(body={"content": [{"text": "ok"}]})
		ai.call_ai(
			ANTHROPIC,
			"key-a",
			"claude-sonnet-4-20250514",
			system_prompt="be terse",
			messages=[{"role": "user", "content": "hi"}],
		)

		self.assertEqual(self.captured["json"]["system"], "be terse")
		self.assertEqual(len(self.captured["json"]["messages"]), 1)

	def test_provider_error_is_surfaced_not_swallowed(self):
		self.stub_requests(status=401, body={"error": {"message": "Invalid API key"}})

		with self.assertRaises(frappe.ValidationError) as caught:
			ai.call_ai(DEEPSEEK, "bad", "deepseek-chat", prompt="hi")

		self.assertIn("Invalid API key", str(caught.exception))

	def test_unexpected_response_shape_throws_rather_than_indexerror(self):
		self.stub_requests(body={"unexpected": True})

		self.assertRaises(frappe.ValidationError, ai.call_ai, DEEPSEEK, "key", "deepseek-chat", prompt="hi")

	def test_missing_prompt_throws(self):
		self.stub_requests(body={"choices": [{"message": {"content": "ok"}}]})
		self.assertRaises(frappe.ValidationError, ai.call_ai, DEEPSEEK, "key", "deepseek-chat")
