import unittest
from unittest.mock import patch
from tools.telegram_setup import select_request, api


def update(chat_id=123, text='/myid', kind='private', date=1000, sender=123):
    return {'message': {'message_id': 4, 'text': text, 'date': date,
                        'chat': {'id': chat_id, 'type': kind},
                        'from': {'id': sender, 'is_bot': False}}}


class SetupTests(unittest.TestCase):
    def test_only_exact_private_command(self):
        for bad in (update(text='hello'), update(kind='group'), update(sender=9), update(date=0)):
            self.assertIsNone(select_request([bad], 4000))
        self.assertEqual(select_request([update()], 1100)['chat']['id'], 123)

    def test_multiple_senders_rejected(self):
        with self.assertRaises(ValueError):
            select_request([update(), update(chat_id=456, sender=456)], 1100)

    def test_duplicate_command_same_person_allowed(self):
        self.assertIsNotNone(select_request([update(), update()], 1100))

    @patch('tools.telegram_setup.urlopen', side_effect=Exception('botSECRET'))
    def test_token_not_in_error(self, mocked):
        with self.assertRaises(ValueError) as err:
            api('SECRET', 'getUpdates', {})
        self.assertNotIn('SECRET', str(err.exception))