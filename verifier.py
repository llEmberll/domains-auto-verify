from imap_tools import MailBox, AND
import re
import time
import logging
import telebot
from telebot import types
from datetime import datetime
from configparser import ConfigParser
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.proxy import Proxy, ProxyType
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


# Инициализация конфига и лога
config = ConfigParser()
config.read("config.ini")
logging.basicConfig(filename=config['LOG']['filename'], level=logging.INFO)


# Настройка мессенджера
bot_token = config['TG']['bot_token']
bot = telebot.TeleBot(bot_token)
chat_id = config['TG']['active_chat_id']


# Установка данных для доступа к почте
gmail_login = config['GMAIL']['login']
gmail_app_pas = config['GMAIL']['app_pas']
gmail_folder = config['GMAIL']['folder']


# Установка пути доступа к браузеру
driver_path = config['DRIVER']['path']


# Получает список писем на тему подтверждения доменов
def get_verify_letters():
    try:
        filter = 'TEXT "IMMEDIATE VERIFICATION required for your domain(s)"'
        verifolder = gmail_folder

        with MailBox('imap.gmail.com').login(gmail_login, gmail_app_pas, initial_folder='INBOX') as mailbox:
            verify_letters = mailbox.fetch(filter)
            mails = [msg.text for msg in verify_letters]

            if len(mails) > 0:
                is_exists = mailbox.folder.exists(verifolder)
                if is_exists == False:
                    mailbox.folder.create(verifolder)

                move = mailbox.move(mailbox.fetch(filter), verifolder)
                print("move: ", move)

                return mails
            else:
                return None


    except Exception as e:
        print(e)
        time_error = datetime.now()
        logging.error(f"\n-------------{time_error}--------------\n:При подключении к почте произшла ошибка:\n{e}")


# Выбирает из текста писем имя домена и ссылку на его подтверждение
def parse_letters(mails):
    domains = []
    domain_case = []
    for mail in mails:
        try:
            mail = str(mail)

            domain = re.findall(r'^[-a-z]{6,60}\.[a-z]{2,10}\b', mail, flags=re.MULTILINE | re.ASCII)[0]

            print("Domain: ", domain)

            if domain in domains:
                print("Данный домен уже встречался")
            else:
                verify_link = (re.findall(r'(^https?://[\S]{36,120})', mail, flags=re.MULTILINE | re.ASCII))
                verify_link = verify_link[0].replace('<br', '')

                print("Link: ", verify_link)

                # Группировка домена с сылкой
                domain_case.append({'domain': domain, 'url': verify_link})
                domains.append(domain)

        except Exception as e:
            print(e)
            time_error = datetime.now()
            logging.error(f"\n-------------{time_error}--------------\n:При обработке текста письма произошла ошибка:\n{e}")

    return domain_case


# Настройка для браузера
def customization_browser():
    chrome_options = webdriver.ChromeOptions()

    chrome_options.add_argument('--disable-gpu')

    chrome_options.add_argument("start-maximized")

    chrome_options.add_argument('--no-sandbox')

    chrome_options.headless = True

    return chrome_options


# Получение браузера
def get_browser(chrome_options):
    try:
        driver = webdriver.Chrome(executable_path=driver_path, chrome_options=chrome_options)
        return driver
    except Exception as e:
        print(e)
        time_error = datetime.now()
        logging.error(f"\n-------------{time_error}--------------\n:Не удалось запустить браузер:\n{e}")


# Переход по ссылке в браузере и получение результатов на странице
def domain_verific(browser, domains):
    success_res = []
    whoops_res = []
    error_res = []
    for domain_case in domains:
        domain = domain_case['domain']
        print("Domain: ", domain)
        browser.get(domain_case['url'])

        element = WebDriverWait(browser, 6).until(EC.presence_of_element_located((By.TAG_NAME, 'h1')))

        print("Result: ", element.text)
        try:
            if 'Success!' in element.text:
                success_res.append(domain)
            elif 'Whoops!' in element.text:
                whoops_res.append(domain)
        except Exception as e:
            print(e)
            error_res.append(domain)
            time_error = datetime.now()
            logging.error(f"\n-------------{time_error}--------------\n:Страница с подтверждением домена вернула неожиданный ответ:\n{e}")

    browser.quit()
    return {'success': success_res, 'whoops': whoops_res, 'error': error_res}


# Настройка отображения результатов подтверждений
def show_verif_res(verify_res, only_wrongs=False):
    res_error = "Процесс подтверждения прошел без ошибок!"

    errors = verify_res['error']
    len_er = len(errors)

    if len_er > 0:
        list = str('\n'.join(errors))

        if only_wrongs == True:
            return f"Domains with contacts verification error({len_er}):\n{list}"
        res_error = f"Домены, которые не удалось подтвердить({len_er}):\n{list}"
    else:
        if only_wrongs == True:
            return None


    res_success = "Успешно подтвержденных доменов нет"
    res_whoops = "Подтвержденных ранее доменов не попалось"


    successes = verify_res['success']
    len_suc = len(successes)

    if len_suc > 0:
        list = str('\n'.join(successes))
        res_success = f"Успешно подтвержденные домены({len_suc}):\n{list}"

    whoopses = verify_res['whoops']
    len_wh = len(whoopses)

    if len_wh > 0:
        list = str('\n'.join(whoopses))
        res_whoops = f"Домены, которые уже были ({len_wh}):\n{list}"

    return "\n\n".join([res_success, res_whoops, res_error])


def send_result(result):
    title = f"*Domains ICANN verification*"
    message_text = f"{title}\n{result}"
    bot.send_message(chat_id, message_text, parse_mode='Markdown')


def main():
    mails = get_verify_letters()
    if mails != None:
        domains = parse_letters(mails)
        print(domains)

        web_browser = get_browser(customization_browser())

        verify_res = domain_verific(web_browser, domains)
        readible_verify_res = show_verif_res(verify_res, True)
        if readible_verify_res != None:
            send_result(readible_verify_res)
    else:
        print("\nНеподтвержденных доменов на почте не обнаружено!\n")

main()