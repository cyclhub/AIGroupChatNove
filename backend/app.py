import json
import os
import secrets
import threading
from datetime import datetime
from functools import wraps
from pathlib import Path
from urllib.parse import quote_plus

from flask import Flask, abort, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import LONGTEXT
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash

from dialogue_processor import convert_chapter, validate_ai_config
from novel_splitter import split_novel_to_chapters


app = Flask(__name__)
CORS(app)

DB_USER = os.getenv("MYSQL_USER", "root")
DB_PASSWORD = quote_plus(os.getenv("MYSQL_PASSWORD", ""))
DB_HOST = os.getenv("MYSQL_HOST", "")
DB_PORT = os.getenv("MYSQL_PORT", "3306")
DB_NAME = os.getenv("MYSQL_DATABASE", "aixs")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.getenv("UPLOAD_FOLDER", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

db = SQLAlchemy(app)
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.getenv("UPLOAD_FOLDER", BASE_DIR / "uploads"))
if not UPLOAD_DIR.is_absolute():
    UPLOAD_DIR = BASE_DIR / UPLOAD_DIR
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

running_jobs = {}
running_jobs_lock = threading.Lock()

MODEL_PROVIDERS = [
    {
        "label": "DeepSeek",
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    {
        "label": "OpenAI",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
    },
    {
        "label": "通义千问",
        "provider": "qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
    },
    {
        "label": "月之暗面 Kimi",
        "provider": "moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    },
    {
        "label": "智谱 GLM",
        "provider": "zhipu",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-flash", "glm-4-plus"],
    },
    {
        "label": "自定义 OpenAI 兼容",
        "provider": "custom",
        "base_url": "",
        "models": ["custom-model"],
    },
]


@app.errorhandler(401)
def handle_unauthorized(_error):
    return jsonify({"error": "请先登录"}), 401


@app.errorhandler(404)
def handle_not_found(_error):
    return jsonify({"error": "资源不存在或无权访问"}), 404


@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255))
    auth_token = db.Column(db.String(128), unique=True)
    api_provider = db.Column(db.String(50), default="deepseek")
    api_base_url = db.Column(db.String(255), default="https://api.deepseek.com")
    api_model = db.Column(db.String(100), default="deepseek-chat")
    api_key = db.Column(db.String(512), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class UserAIConfig(db.Model):
    __tablename__ = "user_ai_configs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, default="默认")
    provider = db.Column(db.String(50), default="deepseek")
    base_url = db.Column(db.String(255), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    api_key = db.Column(db.String(512), nullable=False)
    sort_order = db.Column(db.Integer, default=1, nullable=False)
    is_enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class Novel(db.Model):
    __tablename__ = "novels"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255))
    upload_time = db.Column(db.DateTime, default=datetime.now)
    total_chapters = db.Column(db.Integer, default=0)
    processed_chapters = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default="uploaded")
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)


class Chapter(db.Model):
    __tablename__ = "chapters"
    id = db.Column(db.Integer, primary_key=True)
    novel_id = db.Column(db.Integer, db.ForeignKey("novels.id"), nullable=False)
    chapter_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(255))
    content = db.Column(LONGTEXT)
    is_processed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class DialogueFlow(db.Model):
    __tablename__ = "dialogue_flows"
    id = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey("chapters.id"), nullable=False)
    sequence = db.Column(db.Integer, nullable=False)
    character = db.Column(db.String(100))
    text = db.Column(LONGTEXT)
    created_at = db.Column(db.DateTime, default=datetime.now)


class NovelSquareEntry(db.Model):
    __tablename__ = "novel_square_entries"
    id = db.Column(db.Integer, primary_key=True)
    novel_id = db.Column(db.Integer, db.ForeignKey("novels.id"), nullable=False, unique=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


with app.app_context():
    schema_lock_acquired = False
    try:
        lock_result = db.session.execute(db.text("SELECT GET_LOCK('aixiaoshuo_schema_init', 60)")).scalar()
        schema_lock_acquired = lock_result == 1
        if not schema_lock_acquired:
            raise RuntimeError("数据库初始化锁获取失败，请稍后重启后端服务")

        db.create_all()
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN auth_token VARCHAR(128) NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("CREATE UNIQUE INDEX uq_users_auth_token ON users (auth_token)"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("CREATE UNIQUE INDEX uq_users_username ON users (username)"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE novels ADD COLUMN user_id INT NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE chapters MODIFY content LONGTEXT"))
            db.session.execute(db.text("ALTER TABLE dialogue_flows MODIFY text LONGTEXT"))
            db.session.execute(db.text("SET SESSION innodb_lock_wait_timeout = 120"))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            print(f"升级 LONGTEXT 字段失败，可忽略已兼容的数据库: {exc}")
    finally:
        if schema_lock_acquired:
            try:
                db.session.execute(db.text("SELECT RELEASE_LOCK('aixiaoshuo_schema_init')"))
                db.session.commit()
            except Exception:
                db.session.rollback()


def refresh_processed_count(novel_id: int) -> int:
    processed_count = Chapter.query.filter_by(novel_id=novel_id, is_processed=True).count()
    novel = Novel.query.get(novel_id)
    if novel:
        novel.processed_chapters = processed_count
        if novel.total_chapters and processed_count >= novel.total_chapters:
            novel.status = "completed"
    db.session.commit()
    return processed_count


def previous_chapter_result(novel_id: int, chapter_number: int) -> str:
    prev_chapter = Chapter.query.filter_by(
        novel_id=novel_id,
        chapter_number=chapter_number - 1,
        is_processed=True,
    ).first()
    if not prev_chapter:
        return "无"

    rows = DialogueFlow.query.filter_by(chapter_id=prev_chapter.id).order_by(DialogueFlow.sequence).all()
    if not rows:
        return "无"

    previous = [{"character": row.character, "text": row.text} for row in rows]
    return json.dumps(previous, ensure_ascii=False)


def save_dialogues(chapter: Chapter, dialogues: list[dict]) -> str:
    DialogueFlow.query.filter_by(chapter_id=chapter.id).delete()
    for index, item in enumerate(dialogues, 1):
        db.session.add(
            DialogueFlow(
                chapter_id=chapter.id,
                sequence=index,
                character=item.get("character") or "旁白",
                text=item.get("text") or "",
            )
        )
    chapter.is_processed = True
    db.session.commit()
    return json.dumps(dialogues, ensure_ascii=False)


def process_one_chapter(chapter_id: int, previous_result: str | None = None) -> str | None:
    chapter = Chapter.query.get(chapter_id)
    if not chapter:
        return None
    novel = Novel.query.get(chapter.novel_id)

    reference = previous_result
    if reference is None:
        reference = previous_chapter_result(chapter.novel_id, chapter.chapter_number)

    dialogues = convert_chapter_with_fallback(
        chapter.content or "",
        reference,
        user_ai_configs(novel.user_id if novel else None),
    )
    result = save_dialogues(chapter, dialogues)
    refresh_processed_count(chapter.novel_id)
    return result


def process_chapters_task(novel_id: int, start_chapter: int, end_chapter: int | None, cancel_event: threading.Event) -> None:
    try:
        with app.app_context():
            novel = Novel.query.get(novel_id)
            if not novel:
                return

            novel.status = "processing"
            db.session.commit()

            query = Chapter.query.filter_by(novel_id=novel_id).filter(Chapter.chapter_number >= start_chapter)
            if end_chapter:
                query = query.filter(Chapter.chapter_number <= end_chapter)
            chapters = query.order_by(Chapter.chapter_number).all()
            with running_jobs_lock:
                job = running_jobs.get(novel_id)
                if job and job.get("cancel_event") is cancel_event:
                    job["total"] = len(chapters)
                    job["completed"] = 0

            previous_result = previous_chapter_result(novel_id, start_chapter)
            for chapter in chapters:
                if cancel_event.is_set():
                    novel.status = "cancelled"
                    db.session.commit()
                    return

                try:
                    result = process_one_chapter(chapter.id, previous_result)
                    if result:
                        previous_result = result
                    with running_jobs_lock:
                        job = running_jobs.get(novel_id)
                        if job and job.get("cancel_event") is cancel_event:
                            job["completed"] = int(job.get("completed", 0)) + 1
                    if cancel_event.is_set():
                        novel.status = "cancelled"
                        db.session.commit()
                        return
                except Exception as exc:
                    app.logger.exception("处理小说 %s 第 %s 章失败: %s", novel_id, chapter.chapter_number, exc)
                    novel.status = "failed"
                    db.session.commit()
                    return

            refresh_processed_count(novel_id)
            novel = Novel.query.get(novel_id)
            if novel and novel.status != "completed":
                novel.status = "split"
                db.session.commit()
    finally:
        with running_jobs_lock:
            job = running_jobs.get(novel_id)
            if job and job.get("cancel_event") is cancel_event:
                running_jobs.pop(novel_id, None)


def start_process_thread(novel_id: int, start_chapter: int, end_chapter: int | None) -> bool:
    with running_jobs_lock:
        if novel_id in running_jobs:
            return False
        cancel_event = threading.Event()
        running_jobs[novel_id] = {
            "cancel_event": cancel_event,
            "start_chapter": start_chapter,
            "end_chapter": end_chapter,
            "total": 0,
            "completed": 0,
        }

    thread = threading.Thread(
        target=process_chapters_task,
        args=(novel_id, start_chapter, end_chapter, cancel_event),
        daemon=True,
    )
    thread.start()
    return True


def cancel_process(novel_id: int) -> bool:
    with running_jobs_lock:
        job = running_jobs.get(novel_id)
        if not job:
            return False
        cancel_event = job.get("cancel_event")
        if not cancel_event:
            return False
        cancel_event.set()
        return True


def get_current_user() -> User | None:
    token = (request.headers.get("X-Auth-Token") or request.args.get("token") or "").strip()
    if not token:
        return None
    return User.query.filter_by(auth_token=token).first()


def require_login(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        current_user = get_current_user()
        if not current_user:
            return jsonify({"error": "请先登录"}), 401
        request.current_user = current_user
        return view_func(*args, **kwargs)

    return wrapped


def generate_auth_token() -> str:
    while True:
        token = secrets.token_urlsafe(48)
        if not User.query.filter_by(auth_token=token).first():
            return token


def current_user_or_401() -> User:
    user = getattr(request, "current_user", None) or get_current_user()
    if not user:
        abort(401)
    return user


def owned_novel_or_404(novel_id: int) -> "Novel":
    current_user = current_user_or_401()
    novel = Novel.query.filter_by(id=novel_id, user_id=current_user.id).first()
    if not novel:
        abort(404)
    return novel


def owned_chapter_or_404(chapter_id: int) -> "Chapter":
    current_user = current_user_or_401()
    chapter = (
        Chapter.query.join(Novel, Chapter.novel_id == Novel.id)
        .filter(Chapter.id == chapter_id, Novel.user_id == current_user.id)
        .first()
    )
    if not chapter:
        abort(404)
    return chapter


def square_entry_for_novel(novel_id: int) -> NovelSquareEntry | None:
    return NovelSquareEntry.query.filter_by(novel_id=novel_id).first()


def public_novel_or_404(novel_id: int) -> "Novel":
    novel = Novel.query.get(novel_id)
    if not novel:
        abort(404)
    square_entry = square_entry_for_novel(novel_id)
    if not square_entry or not novel.total_chapters or novel.processed_chapters < novel.total_chapters:
        abort(404)
    return novel


def public_chapter_or_404(chapter_id: int) -> "Chapter":
    chapter = Chapter.query.get(chapter_id)
    if not chapter:
        abort(404)
    if not square_entry_for_novel(chapter.novel_id):
        abort(404)
    return chapter


def mask_api_key(api_key: str | None) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}****{api_key[-4:]}"


def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "api_provider": user.api_provider,
        "api_base_url": user.api_base_url,
        "api_model": user.api_model,
        "api_key_masked": mask_api_key(user.api_key),
        "token": user.auth_token,
        "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def user_ai_config(user_id: int | None) -> dict:
    user = User.query.get(user_id) if user_id else None
    if not user:
        raise ValueError("当前小说没有绑定有效用户，请先完成首次注册后再解析")
    if not user.api_key or not user.api_base_url or not user.api_model:
        raise ValueError("数据库中的大模型配置不完整，请先在模型设置中验证并保存")
    return {
        "api_key": user.api_key,
        "base_url": user.api_base_url,
        "model": user.api_model,
    }


def ai_config_to_dict(config: UserAIConfig) -> dict:
    first_config_id = (
        db.session.query(UserAIConfig.id)
        .filter_by(user_id=config.user_id)
        .order_by(UserAIConfig.id.asc())
        .limit(1)
        .scalar()
    )
    return {
        "id": config.id,
        "name": config.name,
        "provider": config.provider,
        "base_url": config.base_url,
        "model": config.model,
        "api_key_masked": mask_api_key(config.api_key),
        "sort_order": config.sort_order,
        "is_enabled": bool(config.is_enabled),
        "is_builtin": config.id == first_config_id,
        "created_at": config.created_at.strftime("%Y-%m-%d %H:%M:%S") if config.created_at else "",
    }


def ensure_user_ai_configs(user: User | None) -> list[UserAIConfig]:
    if not user:
        return []
    configs = UserAIConfig.query.filter_by(user_id=user.id).order_by(UserAIConfig.sort_order, UserAIConfig.id).all()
    if configs:
        return configs
    if user.api_key and user.api_base_url and user.api_model:
        config = UserAIConfig(
            user_id=user.id,
            name="默认",
            provider=user.api_provider or "deepseek",
            base_url=user.api_base_url,
            model=user.api_model,
            api_key=user.api_key,
            sort_order=1,
            is_enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        return [config]
    return []


def sync_user_primary_ai_config(user: User | None) -> None:
    if not user:
        return
    configs = ensure_user_ai_configs(user)
    primary = next((item for item in configs if item.is_enabled), None) or (configs[0] if configs else None)
    if not primary:
        return
    user.api_provider = primary.provider
    user.api_base_url = primary.base_url
    user.api_model = primary.model
    user.api_key = primary.api_key
    user.updated_at = datetime.now()


def user_ai_configs(user_id: int | None) -> list[dict]:
    user = User.query.get(user_id) if user_id else None
    if not user:
        raise ValueError("当前小说没有绑定有效用户，请先完成注册后再解析章节")
    configs = ensure_user_ai_configs(user)
    enabled_configs = [item for item in configs if item.is_enabled]
    if not enabled_configs:
        raise ValueError("当前账号还没有可用的 AI 配置，请先在模型设置中新增并启用至少一个配置")
    return [
        {
            "id": item.id,
            "name": item.name,
            "provider": item.provider,
            "api_key": item.api_key,
            "base_url": item.base_url,
            "model": item.model,
            "sort_order": item.sort_order,
        }
        for item in enabled_configs
    ]


def user_ai_config(user_id: int | None) -> dict:
    return user_ai_configs(user_id)[0]


def convert_chapter_with_fallback(content: str, previous_result: str, configs: list[dict]) -> list[dict]:
    errors: list[str] = []
    for index, config in enumerate(configs, 1):
        try:
            return convert_chapter(content, previous_result, config)
        except Exception as exc:
            config_name = config.get("name") or f"配置 {index}"
            errors.append(f"{index}. {config_name}（{config.get('model') or 'unknown'}）：{exc}")
    raise RuntimeError("所有 AI 配置调用都失败了：\n" + "\n".join(errors))


def convert_chapter_with_fallback(content: str, previous_result: str, configs: list[dict]) -> list[dict]:
    errors: list[str] = []
    for index, config in enumerate(configs, 1):
        try:
            return convert_chapter(content, previous_result, config)
        except Exception as exc:
            config_name = config.get("name") or f"Config {index}"
            model_name = config.get("model") or "unknown"
            errors.append(f"{index}. {config_name} ({model_name}): {exc}")
    raise RuntimeError("All AI configs failed:\n" + "\n".join(errors))


@app.route("/api/model-providers", methods=["GET"])
def get_model_providers():
    return jsonify(MODEL_PROVIDERS)


@app.route("/api/users", methods=["POST"])
def create_user():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()
    api_key = (payload.get("api_key") or "").strip()
    if not username:
        return jsonify({"error": "请输入用户名"}), 400
    if len(password) < 6:
        return jsonify({"error": "密码至少需要 6 位"}), 400
    if not api_key:
        return jsonify({"error": "请输入大模型 API Key"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "用户名已存在，请直接登录或换一个用户名"}), 400

    ai_config = {
        "api_key": api_key,
        "base_url": payload.get("api_base_url") or "https://api.deepseek.com",
        "model": payload.get("api_model") or "deepseek-chat",
    }
    try:
        validate_ai_config(ai_config)
    except Exception as exc:
        return jsonify({"error": f"模型验证失败：{exc}"}), 400

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        auth_token=generate_auth_token(),
        api_provider=payload.get("api_provider") or "deepseek",
        api_base_url=ai_config["base_url"],
        api_model=ai_config["model"],
        api_key=api_key,
    )
    db.session.add(user)
    db.session.flush()
    db.session.add(
        UserAIConfig(
            user_id=user.id,
            name=(payload.get("config_name") or "默认").strip() or "默认",
            provider=user.api_provider,
            base_url=user.api_base_url,
            model=user.api_model,
            api_key=user.api_key,
            sort_order=1,
            is_enabled=True,
        )
    )
    db.session.commit()
    return jsonify({"success": True, "user": user_to_dict(user)})


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()
    user = User.query.filter_by(username=username).first()
    if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "用户名或密码错误"}), 401
    if not user.auth_token:
        user.auth_token = generate_auth_token()
        db.session.commit()
    return jsonify({"success": True, "user": user_to_dict(user)})


@app.route("/api/logout", methods=["POST"])
@require_login
def logout():
    user = current_user_or_401()
    user.auth_token = generate_auth_token()
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/auth/me", methods=["GET"])
@require_login
def auth_me():
    return jsonify(user_to_dict(current_user_or_401()))


@app.route("/api/users/<int:user_id>", methods=["GET"])
@require_login
def get_user(user_id):
    user = current_user_or_401()
    if user.id != user_id:
        abort(404)
    return jsonify(user_to_dict(user))


@app.route("/api/users/<int:user_id>/model", methods=["PUT"])
@require_login
def update_user_model(user_id):
    user = current_user_or_401()
    if user.id != user_id:
        abort(404)
    payload = request.get_json(silent=True) or {}
    new_api_key = (payload.get("api_key") or user.api_key or "").strip()
    new_base_url = payload.get("api_base_url") or user.api_base_url
    new_model = payload.get("api_model") or user.api_model
    try:
        validate_ai_config(
            {
                "api_key": new_api_key,
                "base_url": new_base_url,
                "model": new_model,
            }
        )
    except Exception as exc:
        return jsonify({"error": f"模型验证失败：{exc}"}), 400

    new_username = (payload.get("username") or user.username).strip()
    if new_username != user.username and User.query.filter_by(username=new_username).first():
        return jsonify({"error": "用户名已存在"}), 400

    user.username = new_username
    configs = ensure_user_ai_configs(user)
    primary = configs[0] if configs else None
    if primary:
        primary.name = (payload.get("config_name") or primary.name or "默认").strip() or "默认"
        primary.provider = payload.get("api_provider") or primary.provider
        primary.base_url = new_base_url
        primary.model = new_model
        primary.api_key = new_api_key
        primary.is_enabled = True
        primary.updated_at = datetime.now()
    sync_user_primary_ai_config(user)
    db.session.commit()
    return jsonify({"success": True, "user": user_to_dict(user)})


@app.route("/api/validate-model", methods=["POST"])
@require_login
def validate_model():
    payload = request.get_json(silent=True) or {}
    try:
        validate_ai_config(
            {
                "api_key": payload.get("api_key") or "",
                "base_url": payload.get("api_base_url") or "",
                "model": payload.get("api_model") or "",
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": f"模型验证失败：{exc}"}), 400
    return jsonify({"success": True, "message": "模型验证成功"})


@app.route("/api/users/<int:user_id>/profile", methods=["PUT"])
@require_login
def update_user_profile(user_id):
    user = current_user_or_401()
    if user.id != user_id:
        abort(404)
    payload = request.get_json(silent=True) or {}
    new_username = (payload.get("username") or user.username).strip()
    if not new_username:
        return jsonify({"error": "请输入账号名"}), 400
    if new_username != user.username and User.query.filter_by(username=new_username).first():
        return jsonify({"error": "用户名已存在"}), 400
    user.username = new_username
    user.updated_at = datetime.now()
    db.session.commit()
    return jsonify({"success": True, "user": user_to_dict(user)})


@app.route("/api/users/<int:user_id>/ai-configs", methods=["GET"])
@require_login
def get_user_ai_configs(user_id):
    user = current_user_or_401()
    if user.id != user_id:
        abort(404)
    configs = ensure_user_ai_configs(user)
    return jsonify([ai_config_to_dict(item) for item in configs])


@app.route("/api/users/<int:user_id>/ai-configs", methods=["POST"])
@require_login
def create_user_ai_config(user_id):
    user = current_user_or_401()
    if user.id != user_id:
        abort(404)
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip() or "未命名配置"
    provider = (payload.get("provider") or "deepseek").strip() or "deepseek"
    base_url = (payload.get("base_url") or "").strip()
    model = (payload.get("model") or "").strip()
    api_key = (payload.get("api_key") or "").strip()
    is_enabled = bool(payload.get("is_enabled", True))
    try:
        validate_ai_config({"api_key": api_key, "base_url": base_url, "model": model})
    except Exception as exc:
        return jsonify({"error": f"模型验证失败：{exc}"}), 400
    max_order = db.session.query(db.func.max(UserAIConfig.sort_order)).filter_by(user_id=user.id).scalar() or 0
    config = UserAIConfig(
        user_id=user.id,
        name=name,
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
        sort_order=max_order + 1,
        is_enabled=is_enabled,
    )
    db.session.add(config)
    db.session.flush()
    sync_user_primary_ai_config(user)
    db.session.commit()
    return jsonify({"success": True, "config": ai_config_to_dict(config), "user": user_to_dict(user)})


@app.route("/api/users/<int:user_id>/ai-configs/<int:config_id>", methods=["PUT"])
@require_login
def update_user_ai_config(user_id, config_id):
    user = current_user_or_401()
    if user.id != user_id:
        abort(404)
    config = UserAIConfig.query.filter_by(id=config_id, user_id=user.id).first_or_404()
    payload = request.get_json(silent=True) or {}
    new_name = (payload.get("name") or config.name).strip() or "未命名配置"
    new_provider = (payload.get("provider") or config.provider).strip() or config.provider
    new_base_url = (payload.get("base_url") or config.base_url).strip()
    new_model = (payload.get("model") or config.model).strip()
    new_api_key = (payload.get("api_key") or config.api_key).strip()
    new_is_enabled = bool(payload.get("is_enabled", config.is_enabled))
    try:
        validate_ai_config({"api_key": new_api_key, "base_url": new_base_url, "model": new_model})
    except Exception as exc:
        return jsonify({"error": f"模型验证失败：{exc}"}), 400
    config.name = new_name
    config.provider = new_provider
    config.base_url = new_base_url
    config.model = new_model
    config.api_key = new_api_key
    config.is_enabled = new_is_enabled
    config.updated_at = datetime.now()
    sync_user_primary_ai_config(user)
    db.session.commit()
    return jsonify({"success": True, "config": ai_config_to_dict(config), "user": user_to_dict(user)})


@app.route("/api/users/<int:user_id>/ai-configs/reorder", methods=["POST"])
@require_login
def reorder_user_ai_configs(user_id):
    user = current_user_or_401()
    if user.id != user_id:
        abort(404)
    payload = request.get_json(silent=True) or {}
    ordered_ids = payload.get("config_ids") or []
    configs = UserAIConfig.query.filter_by(user_id=user.id).all()
    config_map = {item.id: item for item in configs}
    if sorted(config_map.keys()) != sorted(ordered_ids):
        return jsonify({"error": "配置顺序参数不完整"}), 400
    for index, config_id in enumerate(ordered_ids, 1):
        config_map[config_id].sort_order = index
        config_map[config_id].updated_at = datetime.now()
    sync_user_primary_ai_config(user)
    db.session.commit()
    ordered_items = UserAIConfig.query.filter_by(user_id=user.id).order_by(UserAIConfig.sort_order, UserAIConfig.id).all()
    return jsonify({"success": True, "items": [ai_config_to_dict(item) for item in ordered_items], "user": user_to_dict(user)})


@app.route("/api/users/<int:user_id>/ai-configs/<int:config_id>", methods=["DELETE"])
@require_login
def delete_user_ai_config(user_id, config_id):
    user = current_user_or_401()
    if user.id != user_id:
        abort(404)
    config = UserAIConfig.query.filter_by(id=config_id, user_id=user.id).first_or_404()
    first_config_id = (
        db.session.query(UserAIConfig.id)
        .filter_by(user_id=user.id)
        .order_by(UserAIConfig.id.asc())
        .limit(1)
        .scalar()
    )
    if config.id == first_config_id:
        return jsonify({"error": "注册时创建的默认模型配置只能编辑，不能删除"}), 400
    remaining = UserAIConfig.query.filter(UserAIConfig.user_id == user.id, UserAIConfig.id != config_id).count()
    if remaining <= 0:
        return jsonify({"error": "至少保留一个 AI 配置"}), 400
    db.session.delete(config)
    db.session.flush()
    configs = UserAIConfig.query.filter_by(user_id=user.id).order_by(UserAIConfig.sort_order, UserAIConfig.id).all()
    for index, item in enumerate(configs, 1):
        item.sort_order = index
    sync_user_primary_ai_config(user)
    db.session.commit()
    return jsonify({"success": True, "user": user_to_dict(user)})


@app.route("/api/upload", methods=["POST"])
@require_login
def upload_novel():
    if "file" not in request.files:
        return jsonify({"error": "没有文件"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "文件名为空"}), 400

    original_filename = file.filename
    if not original_filename.lower().endswith(".txt"):
        return jsonify({"error": "只支持 txt 小说文件"}), 400

    filename = secure_filename(original_filename) or "novel.txt"
    if "." not in filename:
        filename = f"{os.path.splitext(filename)[0] or 'novel'}.txt"

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    stored_filename = f"{timestamp}_{filename}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], stored_filename)
    file.save(filepath)

    current_user = current_user_or_401()
    novel = Novel(
        title=os.path.splitext(original_filename)[0],
        original_filename=stored_filename,
        user_id=current_user.id if current_user else None,
    )
    db.session.add(novel)
    db.session.commit()

    return jsonify({"success": True, "novel_id": novel.id, "message": "上传成功"})


@app.route("/api/split/<int:novel_id>", methods=["POST"])
@require_login
def split_novel(novel_id):
    novel = owned_novel_or_404(novel_id)
    cancel_process(novel_id)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], novel.original_filename)

    try:
        chapters = split_novel_to_chapters(filepath)
        if not chapters:
            return jsonify({"error": "没有识别到章节，请确认章节标题类似“第1章”"}), 400

        old_chapters = Chapter.query.filter_by(novel_id=novel.id).all()
        old_chapter_ids = [chapter.id for chapter in old_chapters]
        for start in range(0, len(old_chapter_ids), 500):
            batch_ids = old_chapter_ids[start : start + 500]
            DialogueFlow.query.filter(DialogueFlow.chapter_id.in_(batch_ids)).delete(synchronize_session=False)
            Chapter.query.filter(Chapter.id.in_(batch_ids)).delete(synchronize_session=False)
            db.session.commit()

        for index, (title, content) in enumerate(chapters, 1):
            db.session.add(
                Chapter(
                    novel_id=novel.id,
                    chapter_number=index,
                    title=title,
                    content=content,
                )
            )
            if index % 300 == 0:
                db.session.flush()

        novel.total_chapters = len(chapters)
        novel.processed_chapters = 0
        novel.status = "split"
        db.session.commit()

        return jsonify({"success": True, "total_chapters": len(chapters), "message": f"成功分割 {len(chapters)} 个章节"})
    except Exception as exc:
        db.session.rollback()
        print(f"拆分小说 {novel_id} 失败: {exc}")
        return jsonify({"error": f"拆分失败：{exc}"}), 500


@app.route("/api/process/<int:novel_id>", methods=["POST"])
@require_login
def process_novel(novel_id):
    novel = owned_novel_or_404(novel_id)
    current_user = current_user_or_401()
    payload = request.get_json(silent=True) or {}
    start_chapter = int(payload.get("start_chapter") or 1)
    end_chapter = payload.get("end_chapter")
    end_chapter = int(end_chapter) if end_chapter else None

    if not novel.total_chapters:
        return jsonify({"error": "请先拆分章节"}), 400
    if start_chapter < 1 or start_chapter > novel.total_chapters:
        return jsonify({"error": "开始章节超出范围"}), 400
    if end_chapter and end_chapter < start_chapter:
        return jsonify({"error": "结束章节不能小于开始章节"}), 400
    if not novel.user_id:
        if not current_user:
            return jsonify({"error": "请先完成用户注册和模型设置，再解析章节"}), 400
        novel.user_id = current_user.id
        db.session.commit()
    try:
        user_ai_configs(novel.user_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    started = start_process_thread(novel_id, start_chapter, end_chapter)
    return jsonify({"success": True, "message": "开始处理章节" if started else "该范围正在处理中"})


@app.route("/api/process/<int:novel_id>/cancel", methods=["POST"])
@require_login
def cancel_novel_process(novel_id):
    novel = owned_novel_or_404(novel_id)
    cancelled = cancel_process(novel_id)
    if cancelled:
        return jsonify({"success": True, "message": "已发送取消指令，当前正在请求的大模型章节会在返回后停止"})

    if novel.status == "processing":
        novel.status = "cancelled"
        db.session.commit()
    return jsonify({"success": True, "message": "当前没有正在运行的解析任务"})


@app.route("/api/novel/<int:novel_id>", methods=["DELETE"])
@require_login
def delete_novel(novel_id):
    novel = owned_novel_or_404(novel_id)
    cancel_process(novel_id)

    try:
        NovelSquareEntry.query.filter_by(novel_id=novel_id).delete()
        chapters = Chapter.query.filter_by(novel_id=novel_id).all()
        chapter_ids = [chapter.id for chapter in chapters]
        if chapter_ids:
            DialogueFlow.query.filter(DialogueFlow.chapter_id.in_(chapter_ids)).delete(synchronize_session=False)
        Chapter.query.filter_by(novel_id=novel_id).delete()

        filepath = os.path.join(app.config["UPLOAD_FOLDER"], novel.original_filename or "")
        if novel.original_filename and os.path.isfile(filepath):
            os.remove(filepath)

        db.session.delete(novel)
        db.session.commit()
        return jsonify({"success": True, "message": "小说已删除"})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/novel/<int:novel_id>/square", methods=["POST"])
@require_login
def publish_novel_to_square(novel_id):
    novel = owned_novel_or_404(novel_id)
    if not novel.total_chapters or novel.processed_chapters < novel.total_chapters:
        return jsonify({"error": "只有整本解析完成的小说才能发布到广场"}), 400
    entry = square_entry_for_novel(novel.id)
    if not entry:
        entry = NovelSquareEntry(novel_id=novel.id, user_id=novel.user_id or current_user_or_401().id)
        db.session.add(entry)
        db.session.commit()
    return jsonify({"success": True, "message": "已发布到广场"})


@app.route("/api/novel/<int:novel_id>/square", methods=["DELETE"])
@require_login
def unpublish_novel_from_square(novel_id):
    novel = owned_novel_or_404(novel_id)
    deleted = NovelSquareEntry.query.filter_by(novel_id=novel.id).delete()
    db.session.commit()
    if not deleted:
        return jsonify({"success": True, "message": "这本书当前不在广场中"})
    return jsonify({"success": True, "message": "已从广场下架"})


@app.route("/api/novels", methods=["GET"])
@require_login
def get_novels():
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    current_user = current_user_or_401()
    query = Novel.query.filter_by(user_id=current_user.id)
    query = query.order_by(Novel.upload_time.desc())
    total = query.count()
    novels = query.offset((page - 1) * page_size).limit(page_size).all()
    public_novel_ids = {
        item.novel_id
        for item in NovelSquareEntry.query.filter(NovelSquareEntry.novel_id.in_([novel.id for novel in novels])).all()
    } if novels else set()
    items = [
            {
                "id": novel.id,
                "title": novel.title,
                "total_chapters": novel.total_chapters,
                "processed_chapters": novel.processed_chapters,
                "status": novel.status,
                "is_public": novel.id in public_novel_ids,
                "upload_time": novel.upload_time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for novel in novels
        ]
    return jsonify(
        {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size if page_size else 0,
        }
    )


@app.route("/api/square/novels", methods=["GET"])
@require_login
def get_square_novels():
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    try:
        query = (
            db.session.query(NovelSquareEntry, Novel, User)
            .join(Novel, NovelSquareEntry.novel_id == Novel.id)
            .join(User, NovelSquareEntry.user_id == User.id)
            .filter(Novel.total_chapters > 0, Novel.processed_chapters >= Novel.total_chapters)
            .order_by(NovelSquareEntry.created_at.desc())
        )
        total = query.count()
        rows = query.offset((page - 1) * page_size).limit(page_size).all()
        items = [
            {
                "id": novel.id,
                "title": novel.title,
                "total_chapters": novel.total_chapters,
                "processed_chapters": novel.processed_chapters,
                "status": novel.status,
                "is_public": True,
                "owner_username": user.username,
                "upload_time": novel.upload_time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for _entry, novel, user in rows
        ]
        return jsonify(
            {
                "items": items,
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": (total + page_size - 1) // page_size if page_size else 0,
            }
        )
    except Exception as exc:
        db.session.rollback()
        try:
            db.create_all()
            query = (
                db.session.query(NovelSquareEntry, Novel, User)
                .join(Novel, NovelSquareEntry.novel_id == Novel.id)
                .join(User, NovelSquareEntry.user_id == User.id)
                .filter(Novel.total_chapters > 0, Novel.processed_chapters >= Novel.total_chapters)
                .order_by(NovelSquareEntry.created_at.desc())
            )
            total = query.count()
            rows = query.offset((page - 1) * page_size).limit(page_size).all()
            items = [
                {
                    "id": novel.id,
                    "title": novel.title,
                    "total_chapters": novel.total_chapters,
                    "processed_chapters": novel.processed_chapters,
                    "status": novel.status,
                    "is_public": True,
                    "owner_username": user.username,
                    "upload_time": novel.upload_time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for _entry, novel, user in rows
            ]
            return jsonify(
                {
                    "items": items,
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "pages": (total + page_size - 1) // page_size if page_size else 0,
                }
            )
        except Exception as retry_exc:
            db.session.rollback()
            app.logger.exception("获取广场书籍失败: %s", retry_exc)
            return jsonify({"error": "获取广场书籍失败，请检查后端数据库初始化状态"}), 500


@app.route("/api/novel/<int:novel_id>/chapters", methods=["GET"])
@require_login
def get_chapters(novel_id):
    owned_novel_or_404(novel_id)
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    query = Chapter.query.filter_by(novel_id=novel_id).order_by(Chapter.chapter_number)
    total = query.count()
    chapters = query.offset((page - 1) * page_size).limit(page_size).all()
    items = [
            {
                "id": chapter.id,
                "novel_id": chapter.novel_id,
                "chapter_number": chapter.chapter_number,
                "title": chapter.title,
                "is_processed": chapter.is_processed,
            }
            for chapter in chapters
        ]
    return jsonify(
        {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size if page_size else 0,
        }
    )


@app.route("/api/novel/<int:novel_id>/chapter-number/<int:chapter_number>", methods=["GET"])
@require_login
def get_chapter_by_number(novel_id, chapter_number):
    owned_novel_or_404(novel_id)
    chapter = Chapter.query.filter_by(novel_id=novel_id, chapter_number=chapter_number).first_or_404()
    return jsonify(
        {
            "id": chapter.id,
            "novel_id": chapter.novel_id,
            "chapter_number": chapter.chapter_number,
            "title": chapter.title,
            "is_processed": chapter.is_processed,
        }
    )


@app.route("/api/chapter/<int:chapter_id>", methods=["GET"])
@require_login
def get_chapter_detail(chapter_id):
    chapter = owned_chapter_or_404(chapter_id)
    return jsonify(
        {
            "id": chapter.id,
            "novel_id": chapter.novel_id,
            "chapter_number": chapter.chapter_number,
            "title": chapter.title,
            "content": chapter.content,
            "is_processed": chapter.is_processed,
        }
    )


@app.route("/api/chapter/<int:chapter_id>/dialogues", methods=["GET"])
@require_login
def get_dialogues(chapter_id):
    owned_chapter_or_404(chapter_id)
    rows = DialogueFlow.query.filter_by(chapter_id=chapter_id).order_by(DialogueFlow.sequence).all()
    return jsonify(
        [
            {
                "id": row.id,
                "character": row.character,
                "text": row.text,
                "sequence": row.sequence,
            }
            for row in rows
        ]
    )


@app.route("/api/chapter/<int:chapter_id>/next", methods=["GET"])
@require_login
def get_next_chapter(chapter_id):
    chapter = owned_chapter_or_404(chapter_id)
    processed_only = request.args.get("processed_only", "1") != "0"

    query = Chapter.query.filter(
        Chapter.novel_id == chapter.novel_id,
        Chapter.chapter_number > chapter.chapter_number,
    )
    if processed_only:
        query = query.filter(Chapter.is_processed.is_(True))

    next_chapter = query.order_by(Chapter.chapter_number).first()
    if not next_chapter:
        return jsonify({"chapter": None})

    return jsonify(
        {
            "chapter": {
                "id": next_chapter.id,
                "novel_id": next_chapter.novel_id,
                "chapter_number": next_chapter.chapter_number,
                "title": next_chapter.title,
                "is_processed": next_chapter.is_processed,
            }
        }
    )


@app.route("/api/chapter/<int:chapter_id>/prev", methods=["GET"])
@require_login
def get_prev_chapter(chapter_id):
    chapter = owned_chapter_or_404(chapter_id)
    processed_only = request.args.get("processed_only", "1") != "0"

    query = Chapter.query.filter(
        Chapter.novel_id == chapter.novel_id,
        Chapter.chapter_number < chapter.chapter_number,
    )
    if processed_only:
        query = query.filter(Chapter.is_processed.is_(True))

    prev_chapter = query.order_by(Chapter.chapter_number.desc()).first()
    if not prev_chapter:
        return jsonify({"chapter": None})

    return jsonify(
        {
            "chapter": {
                "id": prev_chapter.id,
                "novel_id": prev_chapter.novel_id,
                "chapter_number": prev_chapter.chapter_number,
                "title": prev_chapter.title,
                "is_processed": prev_chapter.is_processed,
            }
        }
    )


@app.route("/api/square/novel/<int:novel_id>/chapters", methods=["GET"])
@require_login
def get_square_chapters(novel_id):
    public_novel_or_404(novel_id)
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    query = Chapter.query.filter_by(novel_id=novel_id).order_by(Chapter.chapter_number)
    total = query.count()
    chapters = query.offset((page - 1) * page_size).limit(page_size).all()
    items = [
        {
            "id": chapter.id,
            "novel_id": chapter.novel_id,
            "chapter_number": chapter.chapter_number,
            "title": chapter.title,
            "is_processed": chapter.is_processed,
        }
        for chapter in chapters
    ]
    return jsonify(
        {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size if page_size else 0,
        }
    )


@app.route("/api/square/chapter/<int:chapter_id>", methods=["GET"])
@require_login
def get_square_chapter_detail(chapter_id):
    chapter = public_chapter_or_404(chapter_id)
    return jsonify(
        {
            "id": chapter.id,
            "novel_id": chapter.novel_id,
            "chapter_number": chapter.chapter_number,
            "title": chapter.title,
            "content": chapter.content,
            "is_processed": chapter.is_processed,
        }
    )


@app.route("/api/square/chapter/<int:chapter_id>/dialogues", methods=["GET"])
@require_login
def get_square_dialogues(chapter_id):
    public_chapter_or_404(chapter_id)
    rows = DialogueFlow.query.filter_by(chapter_id=chapter_id).order_by(DialogueFlow.sequence).all()
    return jsonify(
        [
            {
                "id": row.id,
                "character": row.character,
                "text": row.text,
                "sequence": row.sequence,
            }
            for row in rows
        ]
    )


@app.route("/api/square/chapter/<int:chapter_id>/next", methods=["GET"])
@require_login
def get_square_next_chapter(chapter_id):
    chapter = public_chapter_or_404(chapter_id)
    processed_only = request.args.get("processed_only", "1") != "0"
    query = Chapter.query.filter(
        Chapter.novel_id == chapter.novel_id,
        Chapter.chapter_number > chapter.chapter_number,
    )
    if processed_only:
        query = query.filter(Chapter.is_processed.is_(True))
    next_chapter = query.order_by(Chapter.chapter_number).first()
    if not next_chapter:
        return jsonify({"chapter": None})
    return jsonify(
        {
            "chapter": {
                "id": next_chapter.id,
                "novel_id": next_chapter.novel_id,
                "chapter_number": next_chapter.chapter_number,
                "title": next_chapter.title,
                "is_processed": next_chapter.is_processed,
            }
        }
    )


@app.route("/api/square/chapter/<int:chapter_id>/prev", methods=["GET"])
@require_login
def get_square_prev_chapter(chapter_id):
    chapter = public_chapter_or_404(chapter_id)
    processed_only = request.args.get("processed_only", "1") != "0"
    query = Chapter.query.filter(
        Chapter.novel_id == chapter.novel_id,
        Chapter.chapter_number < chapter.chapter_number,
    )
    if processed_only:
        query = query.filter(Chapter.is_processed.is_(True))
    prev_chapter = query.order_by(Chapter.chapter_number.desc()).first()
    if not prev_chapter:
        return jsonify({"chapter": None})
    return jsonify(
        {
            "chapter": {
                "id": prev_chapter.id,
                "novel_id": prev_chapter.novel_id,
                "chapter_number": prev_chapter.chapter_number,
                "title": prev_chapter.title,
                "is_processed": prev_chapter.is_processed,
            }
        }
    )


@app.route("/api/chapter/<int:chapter_id>/process", methods=["POST"])
@require_login
def process_single_chapter(chapter_id):
    chapter = owned_chapter_or_404(chapter_id)
    novel = Novel.query.get(chapter.novel_id)
    try:
        user_ai_configs(novel.user_id if novel else None)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    started = start_process_thread(chapter.novel_id, chapter.chapter_number, chapter.chapter_number)
    return jsonify({"success": True, "message": "开始转换该章节" if started else "这本小说已有解析任务正在运行"})


@app.route("/api/process/status/<int:novel_id>", methods=["GET"])
@require_login
def get_process_status(novel_id):
    novel = owned_novel_or_404(novel_id)
    processed_count = Chapter.query.filter_by(novel_id=novel_id, is_processed=True).count()
    with running_jobs_lock:
        job = running_jobs.get(novel_id)
        is_running = job is not None
    changed = False
    if processed_count != novel.processed_chapters:
        novel.processed_chapters = processed_count
        changed = True

    task_total = int(job.get("total", 0)) if job else 0
    task_completed = int(job.get("completed", 0)) if job else 0
    task_finished = bool(task_total and task_completed >= task_total)
    novel_finished = bool(novel.total_chapters and processed_count >= novel.total_chapters)

    if is_running and not task_finished and novel.status not in {"failed", "cancelled", "completed", "split"}:
        novel.status = "processing"
        changed = True
    elif not is_running and novel.status == "processing":
        novel.status = "completed" if novel_finished else "split"
        changed = True

    if changed:
        db.session.commit()

    progress_base = task_total if is_running and task_total else novel.total_chapters
    progress_value = task_completed if is_running and task_total else processed_count
    progress = round(progress_value / progress_base * 100, 2) if progress_base else 0
    return jsonify(
        {
            "total_chapters": novel.total_chapters,
            "processed_chapters": processed_count,
            "task_total_chapters": task_total,
            "task_processed_chapters": task_completed,
            "task_start_chapter": job.get("start_chapter") if job else None,
            "task_end_chapter": job.get("end_chapter") if job else None,
            "status": novel.status,
            "progress": progress,
        }
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
