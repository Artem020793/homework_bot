import logging
import os
import sys
import time
import json
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

from exceptions import APIerrorException, SendMessageException

load_dotenv()

logger = logging.getLogger(__name__)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    logger.info('Попытка отправки сообщения')
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except telegram.error.TelegramError:
        raise SendMessageException('Ошибка отправки сообщения')
    else:
        logger.info('Сообщение в чат отправлено')


def get_api_answer(current_timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    timestamp = current_timestamp or int(time.time())
    headers_and_params = {
        'header': {'Authorization': f'OAuth {PRACTICUM_TOKEN}'},
        'param': {'from_date': timestamp}
    }
    try:
        homework_statuses = requests.get(
            ENDPOINT,
            headers=headers_and_params['header'],
            params=headers_and_params['param']
        )
    except requests.exceptions.RequestException as error:
        raise APIerrorException(f'Ошибка при запросе к API: {error}')
    if homework_statuses.status_code != HTTPStatus.OK:
        status_code = homework_statuses.status_code
        raise Exception(f'Ошибка {status_code}')
    try:
        return homework_statuses.json()
    except json.JSONDecodeError:
        raise json.JSONDecodeError('Ошибка перевода ответа из json в Python')


def check_response(response):
    """Проверяет ответ API на корректность."""
    if response['homeworks'] == []:
        text_error = 'От API получен пустой список проверяемых работ.'
        raise TypeError(text_error)
    if 'homeworks' not in response:
        text_error = 'В ответе на запрос отсутствует ключ "homeworks"'
        raise ValueError(text_error)
    homework = response['homeworks']
    if homework[0] is None:
        text_error = 'Нет списка проверяемых работ.'
        raise ValueError(text_error)
    if not isinstance(homework[0], dict):
        text_error = f'Ошибка типа данных! {homework} не словарь!'
        raise TypeError(text_error)
    else:
        return homework


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе.
    статус этой работы.
    """
    if 'homework_name' not in homework:
        raise KeyError('Отсутствует ключ "homework_name" в ответе API')
    if 'status' not in homework:
        raise Exception('Отсутствует ключ "status" в ответе API')
    homework_name = homework['homework_name']
    homework_status = homework['status']
    if homework_status not in HOMEWORK_STATUSES:
        raise Exception(f'Неизвестный статус работы: {homework_status}')
    verdict = HOMEWORK_STATUSES[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет доступность переменных окружения, необходимых для работы.
    Если отсутствует хотя бы одна переменная окружения — функция
    должна вернуть False, иначе — True.
    """
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Отсутствуют токены')
        sys.exit(1)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    start_message = 'Бот начал свою работу!'
    send_message(bot, start_message)
    current_timestamp = int(time.time())
    status_message = ''
    error_message = ''
    while True:
        try:
            response = get_api_answer(current_timestamp)
            current_timestamp = response.get('current_date')
            status = parse_status(check_response(response))
            if status != status_message:
                send_message(bot, status)
                status_message = status
            else:
                info = f'Статус не изменился. Ждем еще {RETRY_TIME} сек.'
                logger.debug(info)
        except Exception as error:
            logger.error(error)
            message = f'Сбой в работе программы: {error}'
            if message != error_message:
                send_message(bot, message)
                error_message = message
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    logging.basicConfig(
        encoding='UTF-8',
        level=logging.INFO,
        format='%(asctime)s, %(levelname)s, %(message)s, %(name)s',
        handlers=[logging.StreamHandler()]
    )
    main()
