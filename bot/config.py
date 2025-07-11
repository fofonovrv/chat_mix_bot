import os
from logging.config import dictConfig
from logging import getLogger, StreamHandler

# BASE_DIR = Path(__file__).resolve().parent.parent
ADMIN_LIST = [id.strip() for id in os.environ.get('ADMIN_LIST','99129974').split(',')]

TG_TOKEN = os.environ.get('TG_TOKEN', '')
DB_USER = os.environ.get('POSTGRES_USER')
DB_PASSWORD = os.environ.get('POSTGRES_PASSWORD')
DB_HOST = 'db_kot'
DB_PORT = '5432'
DB_NAME = os.environ.get('POSTGRES_DB')
if os.environ.get('DB_TYPE') == 'postgres':
	DB_STRING = f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
else:
	DB_STRING = 'sqlite:///db.sqlite3'

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_MODEL = 'gpt-4o-mini'

LOG_LEVEL = os.getenv('LOG_LEVEL','DEBUG')
LOG_FILE = os.getenv('LOG_FILE',f'logs/{LOG_LEVEL.lower()}.log')
LOGGER_NAME = os.getenv('LOGGER_NAME','chat_mix_bot')

GENNADY_PERSONA = {
    "name": "Геннадий",
    "description": (
        "Ты — Геннадий, немного дерзкий занудливый чувак из чата (бот). "
        "Отвечай интересно, но с ехидством и лёгкой грубостью, надменностью, но без злобы. К дамам будь помягче"
        "Не пиши длинных текстов."
    )
}

HELP_TEXT = '''
Этот бот логирует сообщения в чате, отслеживает опросы, реакции и может создавать саммари за определённый период.

Доступные команды:

/help — показать справку  
/summary <дата1> <время1> <дата2> <время2> — создать саммари сообщений за указанный период

Пример:
  /summary 01.07.2025 10:00 01.07.2025 15:00

Обычные сообщения, реакции, опросы и ответы сохраняются, чтобы потом их можно было удобно анализировать или пересматривать.
Сообщения в ответах сохраняются с привязкой к исходному, а GPT-саммари учитывает, кто кому отвечал.
Если в чате создаётся опрос — бот пересоздаёт его от своего имени, чтобы отслеживать голоса.
По всем вопросам — обращайтесь к администратору.
'''

dictConfig({
	'version': 1,
	'disable_existing_loggers': False,
	'formatters': 
		{
		'default': 
			{
			'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
			}
		},
	'handlers': 
		{
		'stdout': 
			{
			'class': 'logging.StreamHandler',
			'formatter': 'default', 
			'stream': 'ext://sys.stdout',
			},
		'file':{
			'formatter':'default',
			'class':'logging.FileHandler',
			'filename': LOG_FILE
		}
	}, 
	'loggers': 
		{
		'': 
			{                  
			'handlers': ['stdout', 'file'],    
			'level': LOG_LEVEL,    
			'propagate': True 
			}
		}
	}
)