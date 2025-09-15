# Customer Support Email Agent

[Перейти к русскому варианту](#russian-version)

## Overview
This project is a **Customer Support Email Agent** (demo version) built to handle incoming emails for a logistics company using the Gmail API, a Retrieval-Augmented Generation (RAG) system for answering questions, and a SQLite database for managing orders and email records. The application categorizes emails into three types: **Question**, **Refund**, or **Other**, processes them accordingly, and provides a user interface via Streamlit for managing Gmail accounts and monitoring email processing.

## Features
- **Gmail Integration**: Connect multiple Gmail accounts, authenticate via OAuth, and disconnect accounts as needed.
- **Email Monitoring**: Continuously monitor unread emails in connected Gmail accounts, processing up to 3 emails per cycle per account.
- **Email Categorization**:
  - **Question**: Uses RAG with a knowledge base (`rag_knowledge_base.txt`) to answer questions. Unanswered questions are logged as unhandled with high importance.
  - **Refund**: Validates order IDs against a database. Valid IDs trigger a refund processing response; invalid or missing IDs prompt the user or log to a not-found table.
  - **Other**: Logs non-sense or unclear emails as unhandled with assessed importance.
- **Database Management**: Stores orders, processed emails, unhandled emails, and invalid refund requests in SQLite.
- **UI**: Streamlit-based interface to connect/disconnect Gmail accounts, start/stop monitoring, and view email history (processed, unhandled, and invalid refunds).

## Example Scenarios
<details>
<summary>Sample Email Interactions</summary>

Below are example email interactions from `test_emails.txt` demonstrating how the agent processes different types of emails:

**1. Question about Pricing**
- **Customer**: Subject: Question about Num pricing  
  Body: Hello, can you tell me what pricing plans are available for a fleet of 20 trucks?
- **Agent**:  
  Subject: Re: Question about Num pricing  
  Body: Num currently offers five tiers:  
  • Free — for very small fleets  
  • Starter  
  • Growth  
  • Scale  
  • Pro  
  A 20-truck operation will most often fit into our Growth or Scale plans, depending on how many dispatcher seats and advanced features (e.g., multi-lane rate shopping, cross-broker bidding, dedicated SLA) you need. To get exact pricing and see a side-by-side feature breakdown, please schedule a demo with our team.

**2. Refund Request with Valid Order ID**
- **Customer**: Subject: Refund request  
  Body: Good day, please process a refund. Order ID: 11111-XYZ.
- **Agent**: Your refund request for Order ID 11111-XYZ will be processed within 3 days.

**3. Refund Request with Invalid Order ID**
- **Customer**: Subject: my mistake  
  Body: Guys, please return money, the order id 00000-WRONG.
- **Agent**: Invalid Order ID: 00000-WRONG. Please verify.
- **Customer**: My order id 00000-WRONG
- **Agent**: (Logged to not_found_refunds table)

**4. Non-sense Email**
- **Customer**: Subject: tea, coffee, dancing?  
  Body: Hi, can you tell me how to order coffee at your office?
- **Agent**: (Logged to unhandled_emails table)

</details>

## Tech Stack
- **Python**: Core programming language.
- **Streamlit**: Web interface for user interaction.
- **Gmail API**: For email reading, sending, and modifying labels.
- **LangChain**: For RAG implementation with OpenAI LLM and embeddings.
- **FAISS**: Vector store for RAG (optional, falls back to LLM if unavailable).
- **SQLite**: Database for storing orders and email records (used for demo purposes).
- **Logging**: For debugging and monitoring application behavior.

## Setup Instructions
1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd customer-support-email-agent
   ```

2. **Install Dependencies**:
   Ensure Python 3.8+ is installed, then install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set Up Gmail API**:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/).
   - Create a project and enable the Gmail API.
   - Create OAuth 2.0 credentials (Desktop app type) and download the `credentials.json` file to the project root.
   - Ensure the Gmail account has the necessary scopes enabled (readonly, send, modify).

4. **Set Up OpenAI API**:
   - Obtain an OpenAI API key from [OpenAI](https://platform.openai.com/).
   - Set the environment variable:
     ```bash
     export OPENAI_API_KEY='your-api-key'
     ```

5. **Prepare Knowledge Base**:
   - Ensure `rag_knowledge_base.txt` is in the project root with the required Q&A format.

6. **Run the Application**:
   ```bash
   streamlit run app.py
   ```

## Usage
1. **Open the App**:
   - Access the Streamlit app in your browser (typically `http://localhost:8501`).
2. **Enter OpenAI API Key**:
   - Input your OpenAI API key when prompted.
3. **Connect Gmail Accounts**:
   - Click "Connect Gmail" and follow the OAuth flow to authenticate accounts.
   - Connected accounts are listed with a "Disconnect" option.
4. **Start Monitoring**:
   - Check "Check latest only" to process only emails from the last day (optional).
   - Click "Start Monitoring" to begin processing unread emails.
   - Stop monitoring with the "Stop Monitoring" button.
5. **View Email History**:
   - Expand the "Extra INFO" section to view processed emails, unhandled questions, and invalid refund requests.
   - Click "Refresh History" to update the displayed data.

## Database Schema
- **orders**: Stores order IDs and their status (`order_id`, `status`).
- **processed_emails_full**: Logs all processed emails (`email_id`, `subject`, `content`, `category`, `importance`, `processed_at`).
- **unhandled_emails**: Stores unanswered questions or other emails (`email_id`, `subject`, `content`, `importance`, `received_at`).
- **not_found_refunds**: Logs invalid refund requests (`email_id`, `subject`, `content`, `invalid_order_id`, `received_at`).
- **pending_refunds**: Tracks refund requests with valid order IDs (`email_id`, `system_reply_id`, `order_id`, `status`, `created_at`).

## Notes
- This is a demo version using SQLite for simplicity and portability. A production version should use PostgreSQL for better scalability.
- The RAG system requires a valid `rag_knowledge_base.txt` file. If FAISS is unavailable, the app falls back to using only the LLM.
- Ensure `credentials.json` is present for Gmail API authentication.
- The app processes up to 3 unread emails per cycle per account to avoid hitting Gmail API rate limits.

## Testing
- Use the provided `test_emails.txt` to simulate email scenarios and verify agent responses (see Example Scenarios above).
- Test cases cover questions, refund requests with valid/invalid order IDs, and non-sense emails.

## Limitations
- This is a demo version; SQLite is used instead of PostgreSQL to simplify setup and deployment. PostgreSQL is recommended for production to handle concurrency better.
- Requires a stable internet connection for Gmail API and OpenAI API calls.
- The RAG system depends on the quality of the knowledge base; incomplete or poorly formatted entries may lead to unhandled questions.
- Error handling is robust but may require manual intervention for persistent API or database issues.

<!-- ## License
This project is licensed under the MIT License. -->

---

# Russian Version
<a name="russian-version"></a>

## Обзор
Этот проект представляет собой **Агент поддержки по электронной почте** (демо-версия), разработанный для обработки входящих писем для логистической компании с использованием Gmail API, системы RAG (Retrieval-Augmented Generation) для ответов на вопросы и базы данных SQLite для управления заказами и записями писем. Приложение классифицирует письма на три типа: **Вопрос**, **Возврат** или **Другое**, обрабатывает их соответствующим образом и предоставляет пользовательский интерфейс через Streamlit для управления учетными записями Gmail и мониторинга обработки писем.

## Возможности
- **Интеграция с Gmail**: Подключение нескольких учетных записей Gmail, аутентификация через OAuth и отключение учетных записей при необходимости.
- **Мониторинг писем**: Постоянный мониторинг непрочитанных писем в подключенных учетных записях Gmail, обработка до 3 писем за цикл для каждой учетной записи.
- **Классификация писем**:
  - **Вопрос**: Использует RAG с базой знаний (`rag_knowledge_base.txt`) для ответов на вопросы. Неотвеченные вопросы сохраняются как необработанные с высоким приоритетом.
  - **Возврат**: Проверяет идентификаторы заказов в базе данных. Для действительных идентификаторов отправляется ответ о обработке возврата в течение 3 дней; для недействительных или отсутствующих идентификаторов запрашивается уточнение или запись в таблицу не найденных возвратов.
  - **Другое**: Сохраняет бессмысленные или неясные письма как необработанные с оценкой уровня важности.
- **Управление базой данных**: Хранит заказы, обработанные письма, необработанные письма и недействительные запросы на возврат в SQLite.
- **Интерфейс**: Интерфейс на основе Streamlit для подключения/отключения учетных записей Gmail, запуска/остановки мониторинга и просмотра истории писем (обработанные, необработанные и недействительные возвраты).

## Примеры сценариев
<details>
<summary>Примеры взаимодействия с письмами</summary>

Ниже приведены примеры взаимодействия с письмами из `test_emails.txt`, демонстрирующие, как агент обрабатывает различные типы писем:

**1. Вопрос о ценах**
- **Клиент**: Тема: Question about Num pricing  
  Тело: Здравствуйте, можете ли вы рассказать о доступных тарифных планах для автопарка из 20 грузовиков?
- **Агент**:  
  Тема: Re: Question about Num pricing  
  Тело: Num предлагает пять тарифных планов:  
  • Free — для очень маленьких автопарков  
  • Starter  
  • Growth  
  • Scale  
  • Pro  
  Для автопарка из 20 грузовиков чаще всего подходят планы Growth или Scale, в зависимости от количества мест для диспетчеров и необходимых функций (например, поиск ставок по нескольким маршрутам, торги между брокерами, выделенный SLA). Для получения точной стоимости и сравнения функций запишитесь на демонстрацию с нашей командой.

**2. Запрос на возврат с действительным ID заказа**
- **Клиент**: Тема: Refund request  
  Тело: Добрый день, пожалуйста, обработайте возврат. ID заказа: 11111-XYZ.
- **Агент**: Ваш запрос на возврат для ID заказа 11111-XYZ будет обработан в течение 3 дней.

**3. Запрос на возврат с недействительным ID заказа**
- **Клиент**: Тема: my mistake  
  Тело: Ребята, пожалуйста, верните деньги, ID заказа 00000-WRONG.
- **Агент**: Недействительный ID заказа: 00000-WRONG. Пожалуйста, проверьте.
- **Клиент**: Мой ID заказа 00000-WRONG
- **Агент**: (Записано в таблицу not_found_refunds)

**4. Бессмысленное письмо**
- **Клиент**: Тема: tea, coffee, dancing?  
  Тело: Привет, подскажите, как заказать кофе в вашем офисе?
- **Агент**: (Записано в таблицу unhandled_emails)

</details>

## Технологический стек
- **Python**: Основной язык программирования.
- **Streamlit**: Веб-интерфейс для взаимодействия с пользователем.
- **Gmail API**: Для чтения, отправки писем и изменения меток.
- **LangChain**: Для реализации RAG с использованием LLM и эмбеддингов OpenAI.
- **FAISS**: Векторное хранилище для RAG (опционально, при отсутствии используется только LLM).
- **SQLite**: База данных для хранения заказов и записей писем (используется для демо-версии).
- **Логирование**: Для отладки и мониторинга поведения приложения.

## Инструкции по установке
1. **Клонирование репозитория**:
   ```bash
   git clone <repository-url>
   cd customer-support-email-agent
   ```

2. **Установка зависимостей**:
   Убедитесь, что установлен Python 3.8+, затем установите необходимые пакеты:
   ```bash
   pip install -r requirements.txt
   ```

3. **Настройка Gmail API**:
   - Перейдите в [Google Cloud Console](https://console.cloud.google.com/).
   - Создайте проект и включите Gmail API.
   - Создайте учетные данные OAuth 2.0 (тип приложения — настольное) и скачайте файл `credentials.json` в корень проекта.
   - Убедитесь, что учетная запись Gmail имеет необходимые разрешения (чтение, отправка, изменение).

4. **Настройка OpenAI API**:
   - Получите API-ключ OpenAI на сайте [OpenAI](https://platform.openai.com/).
   - Установите переменную окружения:
     ```bash
     export OPENAI_API_KEY='your-api-key'
     ```

5. **Подготовка базы знаний**:
   - Убедитесь, что файл `rag_knowledge_base.txt` находится в корне проекта в требуемом формате Q&A.

6. **Запуск приложения**:
   ```bash
   streamlit run app.py
   ```

## Использование
1. **Открытие приложения**:
   - Откройте приложение Streamlit в браузере (обычно `http://localhost:8501`).
2. **Ввод API-ключа OpenAI**:
   - Введите API-ключ OpenAI, когда будет предложено.
3. **Подключение учетных записей Gmail**:
   - Нажмите «Connect Gmail» и следуйте процессу аутентификации OAuth.
   - Подключенные учетные записи отображаются с опцией «Disconnect».
4. **Запуск мониторинга**:
   - Установите флажок «Check latest only», чтобы обрабатывать только письма за последний день (опционально).
   - Нажмите «Start Monitoring», чтобы начать обработку непрочитанных писем.
   - Остановите мониторинг кнопкой «Stop Monitoring».
5. **Просмотр истории писем**:
   - Разверните раздел «Extra INFO», чтобы просмотреть обработанные письма, необработанные вопросы и недействительные запросы на возврат.
   - Нажмите «Refresh History» для обновления отображаемых данных.

## Схема базы данных
- **orders**: Хранит идентификаторы заказов и их статус (`order_id`, `status`).
- **processed_emails_full**: Регистрирует все обработанные письма (`email_id`, `subject`, `content`, `category`, `importance`, `processed_at`).
- **unhandled_emails**: Хранит неотвеченные вопросы или другие письма (`email_id`, `subject`, `content`, `importance`, `received_at`).
- **not_found_refunds**: Регистрирует недействительные запросы на возврат (`email_id`, `subject`, `content`, `invalid_order_id`, `received_at`).
- **pending_refunds**: Отслеживает запросы на возврат с действительными идентификаторами заказов (`email_id`, `system_reply_id`, `order_id`, `status`, `created_at`).

## Примечания
- Это демо-версия, использующая SQLite для простоты и переносимости. Для продакшена рекомендуется использовать PostgreSQL для лучшей масштабируемости.
- Система RAG требует наличия корректного файла `rag_knowledge_base.txt`. При отсутствии FAISS приложение переходит на использование только LLM.
- Убедитесь, что файл `credentials.json` присутствует для аутентификации Gmail API.
- Приложение обрабатывает до 3 непрочитанных писем за цикл для каждой учетной записи, чтобы избежать превышения лимитов Gmail API.

## Тестирование
- Используйте предоставленный файл `test_emails.txt` для моделирования сценариев писем и проверки ответов агента (см. Примеры сценариев выше).
- Тестовые случаи охватывают вопросы, запросы на возврат с действительными/недействительными идентификаторами заказов и бессмысленные письма.

## Ограничения
- Это демо-версия; SQLite используется вместо PostgreSQL для упрощения настройки и развертывания. Для продакшена рекомендуется PostgreSQL для лучшей обработки конкурентности.
- Требуется стабильное интернет-соединение для вызовов Gmail API и OpenAI API.
- Система RAG зависит от качества базы знаний; неполные или плохо отформатированные записи могут привести к необработанным вопросам.
- Обработка ошибок надежна, но может потребовать ручного вмешательства при постоянных проблемах с API или базой данных.

<!-- ## Лицензия
Этот проект лицензирован под лицензией MIT. -->
