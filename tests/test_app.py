import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app as chatbot


class ChatbotWebhookTests(unittest.TestCase):
    def setUp(self) -> None:
        chatbot._conversation_history.clear()
        chatbot._conversation_locks.clear()
        self.client = chatbot.app.test_client()
        self.signature = patch.object(chatbot, "validate_twilio_request", return_value=True)
        self.signature.start()
        self.addCleanup(self.signature.stop)
        self.events = patch.object(chatbot, "dispatch_n8n_event")
        self.event_dispatcher = self.events.start()
        self.addCleanup(self.events.stop)

    @staticmethod
    def completion(text: str) -> SimpleNamespace:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
        )

    def test_health_reports_integrations_without_exposing_credentials(self) -> None:
        with patch.object(chatbot, "openai_client", object()):
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"status": "ok", "ai_configured": True, "n8n_configured": bool(chatbot.N8N_WEBHOOK_URL)},
        )

    def test_webhook_uses_and_retains_bounded_conversation_context(self) -> None:
        fake_openai = MagicMock()
        fake_openai.chat.completions.create.side_effect = [
            self.completion("Olá!"),
            self.completion("A resposta é 42."),
        ]
        with patch.object(chatbot, "openai_client", fake_openai):
            first = self.client.post(
                "/whatsapp",
                data={"From": "whatsapp:+5511999999999", "Body": "Oi"},
            )
            second = self.client.post(
                "/whatsapp",
                data={"From": "whatsapp:+5511999999999", "Body": "Qual é a resposta?"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertIn("Olá!", first.get_data(as_text=True))
        self.assertEqual(second.status_code, 200)
        self.assertIn("A resposta é 42.", second.get_data(as_text=True))
        second_call_messages = fake_openai.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(second_call_messages[1]["content"], "Oi")
        self.assertEqual(second_call_messages[2]["content"], "Olá!")
        self.assertEqual(len(chatbot._conversation_history["whatsapp:+5511999999999"]), 4)
        self.assertEqual(
            [call.args[0] for call in self.event_dispatcher.call_args_list],
            [
                "message.received",
                "message.responded",
                "message.received",
                "message.responded",
            ],
        )

    def test_reset_command_clears_history_without_calling_ai(self) -> None:
        sender = "whatsapp:+5511999999999"
        chatbot._conversation_history[sender] = [{"role": "user", "content": "old context"}]
        fake_openai = MagicMock()
        with patch.object(chatbot, "openai_client", fake_openai):
            response = self.client.post(
                "/whatsapp",
                data={"From": sender, "Body": "limpar conversa"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Conversa reiniciada", response.get_data(as_text=True))
        self.assertNotIn(sender, chatbot._conversation_history)
        fake_openai.chat.completions.create.assert_not_called()

    def test_webhook_rejects_missing_sender_or_message(self) -> None:
        response = self.client.post("/whatsapp", data={"From": "whatsapp:+5511999999999"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Both From and Body are required"})

    def test_webhook_rejects_invalid_twilio_signature(self) -> None:
        with patch.object(chatbot, "validate_twilio_request", return_value=False):
            response = self.client.post(
                "/whatsapp",
                data={"From": "whatsapp:+5511999999999", "Body": "Oi"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "Invalid Twilio signature"})


class N8nDeliveryTests(unittest.TestCase):
    @patch.object(chatbot, "N8N_TIMEOUT_SECONDS", 1.5)
    @patch.object(chatbot, "N8N_WEBHOOK_SECRET", "test-secret")
    @patch.object(chatbot, "N8N_WEBHOOK_URL", "https://n8n.example/webhook/test")
    @patch("app.requests.post")
    def test_delivery_sends_json_and_optional_secret(
        self, post: MagicMock
    ) -> None:
        response = MagicMock()
        post.return_value = response
        payload = {"event": "message.received", "data": {"message": "hello"}}

        chatbot.deliver_n8n_event(payload)

        post.assert_called_once_with(
            "https://n8n.example/webhook/test",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Secret": "test-secret",
            },
            timeout=1.5,
        )
        response.raise_for_status.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
