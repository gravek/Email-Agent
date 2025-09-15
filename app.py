import streamlit as st
import google_auth_oauthlib.flow
import googleapiclient.discovery
import google.auth.transport.requests
import os
import pickle
import base64
from email.mime.text import MIMEText
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA
from langchain.docstore.document import Document
import sqlite3
import re
import time
from datetime import datetime
import logging
import email.utils
import threading

# FAISS
try:
    from langchain_community.vectorstores import FAISS
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('app.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

# Suppress google.auth warning
logging.getLogger('google.auth').setLevel(logging.ERROR)

# Config
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify'
]
CREDENTIALS_FILE = 'credentials.json'
TOKEN_DIR = 'tokens'
DB_FILE = "support.db"
os.makedirs(TOKEN_DIR, exist_ok=True)

# DB
def get_db_connection():
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"DB connect failed: {e}")
        return None

@st.cache_resource
def init_db():
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, status TEXT DEFAULT 'active')")
            cur.execute("CREATE TABLE IF NOT EXISTS unhandled_emails (email_id TEXT PRIMARY KEY, subject TEXT, content TEXT, importance TEXT, received_at TEXT)")
            cur.execute("CREATE TABLE IF NOT EXISTS not_found_refunds (email_id TEXT PRIMARY KEY, subject TEXT, content TEXT, invalid_order_id TEXT, received_at TEXT)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS processed_emails_full (
                    email_id TEXT PRIMARY KEY,
                    subject TEXT,
                    content TEXT,
                    category TEXT,
                    importance TEXT,
                    processed_at TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pending_refunds (
                    email_id TEXT PRIMARY KEY,
                    system_reply_id TEXT,
                    order_id TEXT,
                    status TEXT,
                    created_at TEXT
                )
            """)
            try:
                cur.execute("ALTER TABLE pending_refunds ADD COLUMN system_reply_id TEXT")
            except sqlite3.OperationalError:
                pass
            demo_orders = [
                ('12345-ABC', 'active'),
                ('67890-DEF', 'active'),
                ('11111-XYZ', 'active'),
                ('22222-PQR', 'active'),
                ('33333-STU', 'active')
            ]
            cur.executemany("INSERT OR IGNORE INTO orders (order_id, status) VALUES (?, ?)", demo_orders)
            conn.commit()
    except Exception as e:
        logger.error(f"DB init error: {e}")
    finally:
        conn.close()

# DB queries
@st.cache_data
def get_processed_emails(_):
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM processed_emails_full ORDER BY processed_at DESC LIMIT 50")
        rows = cur.fetchall()
        conn.close()
        if rows:
            df = []
            for row in rows:
                content_trunc = row['content'][:200] + "..." if len(row['content']) > 200 else row['content']
                df.append({
                    'ID': row['email_id'],
                    'Subject': row['subject'] or 'N/A',
                    'Content': content_trunc,
                    'Category': row['category'] or 'N/A',
                    'Importance': row['importance'] or 'N/A',
                    'Processed At': row['processed_at']
                })
            return df
        return None
    except Exception as e:
        logger.error(f"Query processed failed: {e}")
        if conn:
            conn.close()
        return None

@st.cache_data
def get_unhandled_emails(_):
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT email_id, subject, content, importance, received_at FROM unhandled_emails ORDER BY received_at DESC LIMIT 50")
        rows = cur.fetchall()
        conn.close()
        if rows:
            df = []
            for row in rows:
                content_trunc = row['content'][:200] + "..." if len(row['content']) > 200 else row['content']
                df.append({
                    'ID': row['email_id'],
                    'Subject': row['subject'],
                    'Content': content_trunc,
                    'Importance': row['importance'],
                    'Received At': row['received_at']
                })
            return df
        return None
    except Exception as e:
        logger.error(f"Query unhandled failed: {e}")
        if conn:
            conn.close()
        return None

@st.cache_data
def get_not_found_refunds(_):
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT email_id, subject, content, invalid_order_id, received_at FROM not_found_refunds ORDER BY received_at DESC LIMIT 20")
        rows = cur.fetchall()
        conn.close()
        if rows:
            df = []
            for row in rows:
                content_trunc = row['content'][:200] + "..." if len(row['content']) > 200 else row['content']
                df.append({
                    'ID': row['email_id'],
                    'Subject': row['subject'],
                    'Content': content_trunc,
                    'Invalid Order ID': row['invalid_order_id'] or 'missing',
                    'Received At': row['received_at']
                })
            return df
        return None
    except Exception as e:
        logger.error(f"Query refunds failed: {e}")
        if conn:
            conn.close()
        return None

# KB and RAG
@st.cache_data
def load_knowledge_base():
    try:
        if not os.path.exists("rag_knowledge_base.txt"):
            raise FileNotFoundError("rag_knowledge_base.txt not found")
        with open("rag_knowledge_base.txt", "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        documents = []
        current_category = None
        current_qa = []
        for line in lines:
            if line.startswith("# "):
                if current_qa:
                    doc_content = "\n".join(current_qa).strip()
                    if doc_content:
                        documents.append(Document(page_content=doc_content, metadata={"category": current_category}))
                current_qa = []
                current_category = line[2:].strip()
            elif line.strip():
                current_qa.append(line)
        if current_qa:
            doc_content = "\n".join(current_qa).strip()
            if doc_content:
                documents.append(Document(page_content=doc_content, metadata={"category": current_category}))
        return documents
    except Exception as e:
        logger.error(f"KB load failed: {e}")
        return []

@st.cache_resource
def init_rag_components():
    try:
        if "OPENAI_API_KEY" not in os.environ or not os.environ["OPENAI_API_KEY"].strip():
            raise ValueError("No OpenAI API key")
        llm = ChatOpenAI(model="o4-mini")
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small", request_timeout=60.0)
        documents = load_knowledge_base()
        if not documents:
            raise ValueError("No documents")

        # Custom QA prompt
        qa_prompt = PromptTemplate(
            input_variables=["context", "question"],
            template="""
            You are an email assistant of a logistic company. Answer the question based only on the provided context from the knowledge base.
            If you don’t have enough information from the provided context to answer the question, respond only with 'I don’t have enough information' and nothing else.
            Context: {context}
            Question: {question}
            Answer:
            """
        )

        if FAISS_AVAILABLE:
            texts = [doc.page_content for doc in documents]
            metadatas = [doc.metadata for doc in documents]
            vectorstore = FAISS.from_texts(texts, embeddings, metadatas)
            qa_chain = RetrievalQA.from_chain_type(
                llm=llm, 
                chain_type="stuff", 
                retriever=vectorstore.as_retriever(search_kwargs={"k": 3}),
                chain_type_kwargs={"prompt": qa_prompt}
            )
            return llm, embeddings, vectorstore, qa_chain
        else:
            return llm, embeddings, None, None
    except Exception as e:
        logger.error(f"RAG failed: {e}")
        llm = ChatOpenAI(model="o4-mini")
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small", request_timeout=60.0)
        return llm, embeddings, None, None

# Gmail
def get_gmail_service(credentials_file):
    try:
        creds = None
        if os.path.exists(credentials_file):
            with open(credentials_file, 'rb') as token:
                creds = pickle.load(token)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(google.auth.transport.requests.Request())
            else:
                if not os.path.exists(CREDENTIALS_FILE):
                    raise FileNotFoundError(f"{CREDENTIALS_FILE} not found")
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(credentials_file, 'wb') as token:
                pickle.dump(creds, token)
        service = googleapiclient.discovery.build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()
        email = profile['emailAddress']
        return service, email
    except Exception as e:
        logger.error(f"Gmail failed: {e}")
        return None, None

# Process functions
def is_email_processed(conn, email_id):
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("SELECT email_id FROM processed_emails_full WHERE email_id = ?", (email_id,))
        return cur.fetchone() is not None
    except:
        return False

def mark_email_processed_full(conn, email_id, subject, content, category, importance):
    if not conn:
        return
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO processed_emails_full 
                (email_id, subject, content, category, importance, processed_at) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (email_id, subject, content, category, importance, datetime.now().isoformat()))
            conn.commit()
    except Exception as e:
        logger.error(f"Insert processed full failed for {email_id}: {e}")

def insert_pending_refund(conn, email_id, system_reply_id, order_id, status):
    if not conn or not system_reply_id:
        logger.error(f"Cannot insert pending for {email_id}: missing system_reply_id ({system_reply_id})")
        return None
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO pending_refunds 
                (email_id, system_reply_id, order_id, status, created_at) 
                VALUES (?, ?, ?, ?, ?)
            """, (email_id, system_reply_id, order_id, status, datetime.now().isoformat()))
            conn.commit()
        return system_reply_id
    except Exception as e:
        logger.error(f"Insert pending refund failed for {email_id}: {e}")
        return None

def get_pending_by_reply_to(conn, reply_to_id):
    if not conn or not reply_to_id:
        return None
    try:
        cur = conn.cursor()
        normalized_reply_to = reply_to_id.strip()
        cur.execute("""
            SELECT * FROM pending_refunds 
            WHERE system_reply_id = ? AND status = 'asked'
            ORDER BY created_at DESC LIMIT 1
        """, (normalized_reply_to,))
        return cur.fetchone()
    except Exception as e:
        logger.error(f"Get pending by reply_to failed: {e}")
        return None

def delete_pending_refund(conn, email_id):
    if not conn:
        return
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM pending_refunds WHERE email_id = ?", (email_id,))
            conn.commit()
    except Exception as e:
        logger.error(f"Delete pending failed for {email_id}: {e}")

def insert_not_found_refund(conn, email_id, subject, content, invalid_order_id):
    if not conn:
        return
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO not_found_refunds (email_id, subject, content, invalid_order_id, received_at) VALUES (?, ?, ?, ?, ?)",
                        (email_id, subject, content, invalid_order_id, datetime.now().isoformat()))
            conn.commit()
    except Exception as e:
        logger.error(f"Insert not_found_refund failed for {email_id}: {e}")

def clean_content_for_regex(content):
    if not content:
        return ''
    lines = content.split('\n')
    cleaned_lines = []
    for line in lines:
        line_stripped = line.strip()
        if line_stripped and not (
            line_stripped.startswith('>') or 
            line_stripped.startswith('--') or 
            line_stripped.startswith('On ') or 
            line_stripped.startswith('From:') or 
            line_stripped.startswith('Sent:') or 
            line_stripped.startswith('To:') or 
            line_stripped.startswith('Subject:') or 
            'Invalid Order ID' in line_stripped
        ):
            cleaned_lines.append(line)
    return '\n'.join(cleaned_lines)

def categorize_email(llm, content):
    try:
        prompt = PromptTemplate(
            input_variables=["email_content"],
            template="""
            You are an email assistant of a logistic company. Please use the knowledge base examples to answer emails.
            Read carefully all the contents of the email thread, including quotes and previous responses.
            Categorize the following email into one of three categories: 'Refund', 'Question' or 'Other'.
            - Categorize as 'Refund':
                - if the email mentions 'refund' or 'return'
                - if the email has 'Invalid Order ID' in replies, quotes a previous refund response, or continues a refund thread (e.g., provides ID after ask)
            - If the email asks for information or clarification about the company or it's services, categorize as 'Question'.
            - If you don’t have enough information to answer the question, say litterly 'I don’t have enough information'.
            - Otherwise, categorize as 'Other'.
            Provide a brief explanation and an importance level (low, medium, high).
            Email content: {email_content}
            Response format:
            Category: <category>
            Explanation: <explanation>
            Importance: <importance>
            """
        )
        response = llm.invoke(prompt.format(email_content=content)).content
        category_match = re.search(r'Category:\s*(\w+)', response, re.IGNORECASE)
        importance_match = re.search(r'Importance:\s*(\w+)', response, re.IGNORECASE)
        if category_match and importance_match:
            return category_match.group(1).strip(), "N/A", importance_match.group(1).strip().lower()
        return "Other", "Failed", "low"
    except:
        return "Other", "Failed", "low"

def process_question_email(qa_chain, email_id, subject, content, sender_email, service, conn, category, importance):
    if is_email_processed(conn, email_id):
        return
    try:
        if not qa_chain:
            process_other_email(email_id, subject, content, importance, sender_email, conn, category)
            return
        result = qa_chain.invoke({"query": content})
        answer = result["result"]
        if "i don’t have enough information" in answer.lower():
            with conn:
                cur = conn.cursor()
                cur.execute("INSERT OR IGNORE INTO unhandled_emails (email_id, subject, content, importance, received_at) VALUES (?, ?, ?, ?, ?)",
                            (email_id, subject, content, importance, datetime.now().isoformat()))
                conn.commit()
        else:
            send_email(service, sender_email, email_id, f"Re: {subject}", answer)
        mark_email_processed_full(conn, email_id, subject, content, category, importance)
    except Exception as e:
        logger.error(f"Question process error {email_id}: {e}")
        mark_email_processed_full(conn, email_id, subject, content, category, importance)

def process_refund_email(email_id, subject, content, sender_email, service, conn, category, reply_to, importance):
    if is_email_processed(conn, email_id):
        return
    try:
        cleaned_content = clean_content_for_regex(content)
        order_id_match = re.search(r'(?:Order\s+ID|order\s+id)[:\s]+([A-Za-z0-9\-]+)', cleaned_content, re.IGNORECASE)
        order_id = order_id_match.group(1) if order_id_match else None

        pending = get_pending_by_reply_to(conn, reply_to)

        if pending:
            if order_id is None:
                invalid_id = pending['order_id'] if pending['order_id'] else 'no_id_provided'
                insert_not_found_refund(conn, email_id, subject, content, invalid_id)
                delete_pending_refund(conn, pending['email_id'])
                final_msg = "We couldn't process your refund request as no valid Order ID was provided. If you have a valid order, please start a new conversation."
                send_email(service, sender_email, email_id, f"Re: {subject}", final_msg)
            else:
                if pending['order_id'] and order_id == pending['order_id']:
                    insert_not_found_refund(conn, email_id, subject, content, order_id)
                    delete_pending_refund(conn, pending['email_id'])
                    final_msg = f"Invalid Order ID {order_id} provided again. Refund request closed."
                    send_email(service, sender_email, email_id, f"Re: {subject}", final_msg)
                else:
                    delete_pending_refund(conn, pending['email_id'])
                    with conn:
                        cur = conn.cursor()
                        cur.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,))
                        result = cur.fetchone()
                        if result:
                            cur.execute("UPDATE orders SET status = 'refund_requested' WHERE order_id = ?", (order_id,))
                            conn.commit()
                            send_email(service, sender_email, email_id, f"Re: {subject}", f"Your refund request for Order ID {order_id} will be processed within 3 days.")
                        else:
                            invalid_msg = f"Invalid Order ID: {order_id}. Please verify and reply with a valid one."
                            system_reply_id = send_email(service, sender_email, email_id, f"Re: {subject}", invalid_msg)
                            if system_reply_id:
                                insert_pending_refund(conn, email_id, system_reply_id, order_id, 'asked')
                            else:
                                logger.error(f"Failed to create pending for different invalid ID {order_id}: send failed")
        else:
            if order_id is None:
                ask_msg = "Please provide the Order ID in the format 'Order ID: XXXXX' (e.g., Order ID: 12345-ABCDE)."
                system_reply_id = send_email(service, sender_email, email_id, f"Re: {subject}", ask_msg)
                if system_reply_id:
                    insert_pending_refund(conn, email_id, system_reply_id, None, 'asked')
                else:
                    logger.error(f"Failed to create pending for missing ID: send failed")
            else:
                with conn:
                    cur = conn.cursor()
                    cur.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,))
                    result = cur.fetchone()
                    if result:
                        cur.execute("UPDATE orders SET status = 'refund_requested' WHERE order_id = ?", (order_id,))
                        conn.commit()
                        send_email(service, sender_email, email_id, f"Re: {subject}", f"Your refund request for Order ID {order_id} will be processed within 3 days.")
                    else:
                        invalid_msg = f"Invalid Order ID: {order_id}. Please verify and reply with a valid one using format like 'Order ID: XXXXX'. Please keep this conversation in your reply."
                        system_reply_id = send_email(service, sender_email, email_id, f"Re: {subject}", invalid_msg)
                        if system_reply_id:
                            insert_pending_refund(conn, email_id, system_reply_id, order_id, 'asked')
                        else:
                            logger.error(f"Failed to create pending for invalid ID {order_id}: send failed")

        mark_email_processed_full(conn, email_id, subject, content, category, importance)
    except Exception as e:
        logger.error(f"Refund process error {email_id}: {e}")
        mark_email_processed_full(conn, email_id, subject, content, category, importance)

def process_other_email(email_id, subject, content, importance, sender_email, conn, category):
    if is_email_processed(conn, email_id):
        return
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO unhandled_emails (email_id, subject, content, importance, received_at) VALUES (?, ?, ?, ?, ?)",
                        (email_id, subject, content, importance, datetime.now().isoformat()))
            conn.commit()
        mark_email_processed_full(conn, email_id, subject, content, category, importance)
    except Exception as e:
        logger.error(f"Other process error {email_id}: {e}")
        mark_email_processed_full(conn, email_id, subject, content, category, importance)

def send_email(service, to_email, in_reply_to, subject, message_text):
    try:
        message = MIMEText(message_text)
        message['To'] = to_email
        message['Subject'] = subject
        if in_reply_to:
            message['In-Reply-To'] = in_reply_to
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = service.users().messages().send(userId='me', body={'raw': raw}).execute()
        gmail_id = sent['id']
        
        sent_msg = service.users().messages().get(userId='me', id=gmail_id, format='full').execute()
        headers = {h['name']: h['value'] for h in sent_msg['payload']['headers']}
        
        message_id = headers.get('Message-Id') or headers.get('Message-ID')
        
        if message_id:
            logger.info(f"Sent email with Message-ID: {message_id} (Gmail ID: {gmail_id})")
            return message_id
        else:
            logger.warning(f"Sent email but no Message-ID found (Gmail ID: {gmail_id}). Available headers: {list(headers.keys())}")
            return None
    except Exception as e:
        logger.error(f"Send email failed: {e}")
        return None

# Monitor
def monitor_emails(llm, qa_chain, latest_only, event, processed_counter):
    logger.info("Monitoring started")
    while event.is_set():
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                time.sleep(60)
                continue
            q_filter = "is:unread newer_than:1d" if latest_only else "is:unread"
            token_files = [f for f in os.listdir(TOKEN_DIR) if f.endswith('.pickle')]
            if not token_files or not event.is_set():
                time.sleep(60)
                continue
            cycle_count = 0
            for token_file in token_files:
                if not event.is_set():
                    break
                service, _ = get_gmail_service(os.path.join(TOKEN_DIR, token_file))
                if not service:
                    continue
                try:
                    results = service.users().messages().list(userId='me', labelIds=['INBOX', 'UNREAD'], q=q_filter, maxResults=3).execute()
                    messages = results.get('messages', [])
                    for message in messages:
                        if not event.is_set():
                            break
                        try:
                            msg = service.users().messages().get(userId='me', id=message['id'], format='full').execute()
                            email_id = message['id']
                            if is_email_processed(conn, email_id):
                                continue
                            headers = {h['name']: h['value'] for h in msg['payload']['headers']}
                            subject = headers.get('Subject', '')
                            from_header = headers.get('From', '')
                            sender_name, sender_email = email.utils.parseaddr(from_header)
                            if not sender_email:
                                sender_email = 'unknown@example.com'
                            reply_to = headers.get('In-Reply-To', '').strip()
                            content = ''
                            payload = msg['payload']
                            if 'parts' in payload:
                                for part in payload['parts']:
                                    if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                                        content = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                                        break
                            else:
                                if payload['mimeType'] == 'text/plain' and 'data' in payload['body']:
                                    content = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
                            if not content or len(content.strip()) < 10:
                                continue
                            category, _, importance = categorize_email(llm, content)
                            if category == 'Question':
                                process_question_email(qa_chain, email_id, subject, content, sender_email, service, conn, category, importance)
                            elif category == 'Refund':
                                process_refund_email(email_id, subject, content, sender_email, service, conn, category, reply_to, importance)
                            else:
                                process_other_email(email_id, subject, content, importance, sender_email, conn, category)
                            logger.info(f"Processed email {email_id}: category {category}, reply_to '{reply_to}'")
                            service.users().messages().modify(userId='me', id=email_id, body={'removeLabelIds': ['UNREAD']}).execute()
                            cycle_count += 1
                            processed_counter[0] += 1
                            time.sleep(1)
                        except Exception as e:
                            logger.error(f"Email process error {email_id}: {e}")
                            pass
                except Exception as e:
                    logger.error(f"Gmail list error for {token_file}: {e}")
                    pass
            logger.info(f"Cycle processed: {cycle_count} across {len(token_files)} accounts")
            if conn:
                conn.close()
            if event.is_set():
                time.sleep(60)
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            if conn:
                conn.close()
            time.sleep(60)
    logger.info("Monitoring stopped")

# Main
def main():
    if 'monitoring' not in st.session_state:
        st.session_state.monitoring = False
    if 'processed_count' not in st.session_state:
        st.session_state.processed_count = 0

    st.set_page_config(page_title="Support", page_icon="📧")
    st.title("Customer Support Email Agent")

    if "OPENAI_API_KEY" not in os.environ or not os.environ["OPENAI_API_KEY"].strip():
        api_key = st.text_input("OpenAI API Key:", type="password")
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key.strip()
            st.rerun()
        else:
            st.warning("Enter OpenAI key.")
            return

    init_db()

    st.header("Gmail")
    if st.button("Connect Gmail"):
        with st.spinner("Connecting to Gmail..."):
            try:
                if not os.path.exists(CREDENTIALS_FILE):
                    st.error(f"{CREDENTIALS_FILE} not found!")
                    st.stop()
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
                token_file = os.path.join(TOKEN_DIR, f"token_{datetime.now().timestamp()}.pickle")
                with open(token_file, 'wb') as token:
                    pickle.dump(creds, token)
                service, email = get_gmail_service(token_file)
                if service:
                    st.success(f"Connected: {email}")
                else:
                    st.error("Connect failed.")
                st.rerun()
            except Exception as e:
                st.error(f"Connect failed: {e}")

    st.subheader("Connected Accounts")
    token_files = [f for f in os.listdir(TOKEN_DIR) if f.endswith('.pickle')]
    if token_files:
        for token_file in token_files:
            service, email = get_gmail_service(os.path.join(TOKEN_DIR, token_file))
            if service:
                col1, col2 = st.columns([3, 1])
                col1.write(email)
                if col2.button(f"Disconnect {email[:20]}...", key=email):
                    os.remove(os.path.join(TOKEN_DIR, token_file))
                    st.session_state.processed_count = 0
                    st.success(f"Disconnected {email}")
                    st.rerun()
    else:
        st.info("No accounts connected.")

    if not token_files:
        st.warning("Connect Gmail to monitor.")

    st.header("System")
    with st.spinner("Initializing RAG..."):
        llm, embeddings, vectorstore, qa_chain = init_rag_components()
    if qa_chain or llm:
        status = "Full QA" if qa_chain else "LLM only"
        st.success(f"RAG: {status}")
    else:
        st.error("RAG failed.")

    if token_files and llm:
        latest_only = st.checkbox("Check latest only (newer_than:1d)", value=False)
        col_start, col_stop = st.columns(2)
        if col_start.button("Start Monitoring (3/cycle per account)"):
            if not st.session_state.monitoring:
                st.session_state.monitoring = True
                event = threading.Event()
                event.set()
                st.session_state.monitor_event = event
                processed_counter = [st.session_state.processed_count]
                thread = threading.Thread(target=monitor_emails, args=(llm, qa_chain, latest_only, event, processed_counter), daemon=True)
                thread.start()
                st.session_state.processed_count = processed_counter[0]
                st.success("Started!")
                st.rerun()
        if st.session_state.monitoring and col_stop.button("Stop Monitoring"):
            st.session_state.monitoring = False
            if 'monitor_event' in st.session_state:
                st.session_state.monitor_event.clear()
            st.success("Stopped!")
            st.rerun()
        if st.session_state.monitoring:
            st.info(f"Monitoring active... Total processed: {st.session_state.processed_count}")


    with st.expander("Extra INFO", expanded=False):
        st.subheader("Email History")
        col_refresh, _ = st.columns(2)
        if col_refresh.button("Refresh History"):
            get_processed_emails.clear()
            get_unhandled_emails.clear()
            get_not_found_refunds.clear()
            st.rerun()

        with st.expander("Processed Emails (last 50)"):
            processed_data = get_processed_emails(None)
            if processed_data:
                st.dataframe(processed_data)
            else:
                st.info("No processed emails. Run monitoring on unread emails.")

        with st.expander("Unhandled Questions (last 50)"):
            unhandled_data = get_unhandled_emails(None)
            if unhandled_data:
                st.dataframe(unhandled_data)
            else:
                st.info("No unhandled emails.")

        with st.expander("Invalid Refunds (last 20)"):
            refunds_data = get_not_found_refunds(None)
            if refunds_data:
                st.dataframe(refunds_data)
            else:
                st.info("No invalid refunds.")

if __name__ == "__main__":
    main()