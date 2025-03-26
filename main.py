import telebot
from telebot import types
import requests
import json
import os
import logging

TOKEN = 'YOUR_BOT_TOKEN'
bot = telebot.TeleBot(TOKEN)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_URL = 'https://official-joke-api.appspot.com/random_joke'
MAX_JOKE_ATTEMPTS = 10
REQUEST_TIMEOUT = 5
JOKES_FILE = 'best_jokes.json'


class UserState:
    def init(self):
        self.jokes = {}
        self.submissions = []
        self.states = {}


user_state = UserState()


def save_joke(joke):
    try:
        with open(JOKES_FILE, 'a', encoding='utf-8') as f:
            json_joke = {
                'text': f"{joke.get('setup', '')} - {joke.get('punchline', '')}",
                'source': 'user' if 'user_id' in joke else 'api'
            }
            if 'user_id' in joke:
                json_joke['user_id'] = joke['user_id']
            f.write(json.dumps(json_joke, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.error(f"Error saving joke: {e}")


def load_jokes():
    if not os.path.exists(JOKES_FILE):
        return []

    jokes = []
    try:
        with open(JOKES_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    joke = json.loads(line)
                    if isinstance(joke, dict) and 'text' in joke:
                        jokes.append(joke)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON line: {line}")
    except Exception as e:
        logger.error(f"Error loading jokes: {e}")

    return jokes


def fetch_joke():
    try:
        response = requests.get(API_URL, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
    return None


def find_joke_by_keyword(keyword):
    for _ in range(MAX_JOKE_ATTEMPTS):
        joke = fetch_joke()
        if joke and keyword.lower() in joke.get('setup', '').lower():
            return joke
        if joke and keyword.lower() in joke.get('punchline', '').lower():
            return joke
    return None


@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "ദ്ദി •⩊• )\n\nHi! I'm JokesBot\n"
        "Available commands:\n"
        "/jokes - Get 4 random jokes\n"
        "/best_jokes - Show saved jokes\n"
        "/find_joke - Search joke by keyword"
    )
    bot.reply_to(message, welcome_text)


@bot.message_handler(commands=['find_joke'])
def ask_for_keyword(message):
    msg = bot.send_message(message.chat.id, "Please enter a keyword to search:")
    user_state.states[message.chat.id] = {'state': 'awaiting_keyword'}
    bot.register_next_step_handler(msg, process_keyword_search)


def process_keyword_search(message):
    chat_id = message.chat.id
    keyword = message.text.strip()

    if not keyword:
        bot.send_message(chat_id, "Please enter a valid keyword.")
        return

    bot.send_message(chat_id, f"Searching for jokes with '{keyword}'...")

    if found_joke := find_joke_by_keyword(keyword):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Save Joke", callback_data=f"save_{keyword}"))
        bot.send_message(chat_id, f"Found joke:\n\n{found_joke['setup']} - {found_joke['punchline']}",
                         reply_markup=markup)
    else:
        bot.send_message(chat_id, f"No jokes found containing '{keyword}'. Try another word.")

    user_state.states.pop(chat_id, None)

    @bot.message_handler(commands=['jokes'])
    def send_jokes(message):
        jokes = []
        for _ in range(4):
            if joke := fetch_joke():
                jokes.append(f"{joke['setup']} - {joke['punchline']}")

        if not jokes:
            bot.reply_to(message, "Couldn't fetch any jokes. Please try again later.")
            return

        user_state.jokes[message.chat.id] = jokes

        markup = types.InlineKeyboardMarkup(row_width=4)
        buttons = [types.InlineKeyboardButton(str(i + 1), callback_data=str(i)) for i in range(len(jokes))]
        markup.add(*buttons)
        markup.add(types.InlineKeyboardButton("Add Your Own", callback_data="add_joke"))

        jokes_text = "Here are your jokes:\n" + "\n".join(
            f"{i + 1}. {joke}" for i, joke in enumerate(jokes)
        )
        bot.send_message(message.chat.id, jokes_text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("save_"))
    def save_joke_handler(call):
        chat_id = call.message.chat.id
        joke_text = call.message.text.split('\n\n', 1)[-1]
        save_joke({'setup': joke_text.split(' - ')[0], 'punchline': joke_text.split(' - ')[1]})
        bot.answer_callback_query(call.id, "Joke saved successfully!")

    @bot.callback_query_handler(func=lambda call: call.data == "add_joke")
    def request_custom_joke(call):
        msg = bot.send_message(call.message.chat.id, "Send your joke in format:\nSetup - Punchline")
        user_state.states[call.message.chat.id] = {'state': 'awaiting_custom_joke'}
        bot.register_next_step_handler(msg, process_custom_joke)

    def process_custom_joke(message):
        chat_id = message.chat.id
        try:
            setup, punchline = map(str.strip, message.text.split(' - ', 1))
            save_joke({
                'setup': setup,
                'punchline': punchline,
                'user_id': message.from_user.id
            })
            bot.send_message(chat_id, "Your joke has been saved!")
        except ValueError:
            bot.send_message(chat_id, "Invalid format. Please use: Setup - Punchline")
        finally:
            user_state.states.pop(chat_id, None)

    @bot.message_handler(commands=['best_jokes'])
    def show_best_jokes(message):
        jokes = load_jokes()

        if not jokes:
            bot.reply_to(message, "No saved jokes yet. Be the first to add one!")
            return

        response = "🌟 Top Saved Jokes 🌟\n\n" + "\n\n".join(
            f"{i + 1}. {joke['text']}" for i, joke in enumerate(jokes)
        )
        bot.reply_to(message, response[:4000])

    if __name__ == 'main':
        if not os.path.exists(JOKES_FILE):
            open(JOKES_FILE, 'w').close()

        logger.info("Starting bot...")
        bot.polling()