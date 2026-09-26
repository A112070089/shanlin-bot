from __future__ import annotations
import uvicorn
import json
import os
import re
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    import firebase_admin
    from firebase_admin import credentials, db
except Exception:
    firebase_admin = None
    credentials = None
    db = None

from typing import Any

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
)

from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field

from dotenv import load_dotenv


try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


from self_pay_api import router as self_pay_router


# ==========================================================
# FastAPI
# ==========================================================

app = FastAPI()

# ==========================================================
# Firebase
# ==========================================================
FIREBASE_URL = os.environ.get("FIREBASE_URL", "")
FIREBASE_CREDENTIALS = os.environ.get("FIREBASE_CREDENTIALS", "")


def init_firebase():
    if firebase_admin is None:
        print("Firebase admin SDK not installed.")
        return False

    if firebase_admin._apps:
        return True

    if not FIREBASE_URL:
        print("Firebase init skipped: FIREBASE_URL is empty.")
        return False

    if not FIREBASE_CREDENTIALS:
        print("Firebase init skipped: FIREBASE_CREDENTIALS is empty.")
        return False

    try:
        cred_dict = json.loads(FIREBASE_CREDENTIALS)

        if cred_dict.get("type") != "service_account":
            print("Firebase init skipped: invalid service account.")
            return False

        cred = credentials.Certificate(cred_dict)

        firebase_admin.initialize_app(
            cred,
            {
                "databaseURL": FIREBASE_URL
            }
        )

        print("Firebase initialized successfully.")
        return True

    except Exception as e:
        print(f"Firebase init failed: {e}")
        return False


# ==========================================================
# CORS
# ==========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================================
# 自費項目 API
# ==========================================================

app.include_router(self_pay_router)


# ==========================================================
# 載入 .env
# ==========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

load_dotenv(
    os.path.join(
        BASE_DIR,
        ".env",
    )
)

GROQ_API_KEY = (
    os.getenv(
        "GROQ_API_KEY",
        "",
    )
    .strip()
)


print("=" * 60)

print(
    "Groq Key Loaded :",
    bool(GROQ_API_KEY),
)

if GROQ_API_KEY:

    print(
        "Groq Key Prefix :",
        GROQ_API_KEY[:12] + "...",
    )

else:

    print(
        "Groq Key NOT FOUND"
    )

print("=" * 60)


# ==========================================================
# Groq / OpenAI Client
# ==========================================================

client = (
    OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )
    if (
        GROQ_API_KEY
        and OpenAI
    )
    else None
)


# ==========================================================
# database.json
# ==========================================================

DB_PATH = os.path.join(
    BASE_DIR,
    "database.json",
)


with open(
    DB_PATH,
    encoding="utf-8",
) as _f:

    _DB = json.load(_f)


NAME_DB = _DB["NAME_DB"]


# ==========================================================
# Whisper 幻覺過濾
# ==========================================================

HALLUCINATION_EXACT = {
    "謝謝",
    "謝謝收看",
    "謝謝觀看",
    "請訂閱",
    "感謝收聽",
    ".",
    "。",
    "，",
    " ",
    "　",
}


HALLUCINATION_CONTAINS = [

    "谢谢大家",
    "謝謝大家",
    "WILL ",
    "點讚",
    "訂閱",
    "轉發",

    "明镜",
    "頻道",
    "打開小鈴鐺",
    "MING PAO",
    "CANADA",
    "TORONTO",

    "澳洲",
    "加拿大",
    "報紙",
    "DANGER",
    "AMARA",
    "SUBTITLE",

    "谢谢",
    "点赞",
    "订阅",
    "转发",

    "YIXI.TV",
    "YIXI",
]


def is_hallucination(
    text: str,
) -> bool:

    t = text.strip()

    if (
        not t
        or t
        in HALLUCINATION_EXACT
    ):

        return True


    for h in HALLUCINATION_CONTAINS:

        if h in t.upper():

            return True


    # 日文假訊號
    if re.search(
        r"[\u3040-\u30FF]",
        t,
    ):

        return True


    if (
        len(
            re.sub(
                r"[^\w]",
                "",
                t,
            )
        )
        == 0
    ):

        return True


    return False


# ==========================================================
# 姓名拆字資料庫
# ==========================================================

def resolve_name_from_db(
    text: str,
) -> str:

    if not text:

        return ""


    matches = []

    used_ranges = []


    sorted_keys = sorted(
        NAME_DB.keys(),
        key=len,
        reverse=True,
    )


    for key in sorted_keys:

        idx = 0

        while True:

            pos = text.find(
                key,
                idx,
            )

            if pos == -1:

                break


            end = (
                pos
                + len(key)
            )


            if not any(
                s < end
                and pos < e
                for s, e
                in used_ranges
            ):

                matches.append(
                    (
                        pos,
                        end,
                        NAME_DB[key],
                    )
                )

                used_ranges.append(
                    (
                        pos,
                        end,
                    )
                )


            idx = pos + 1


    for m in re.finditer(
        r"[\u4e00-\u9fff]{1,8}的([\u4e00-\u9fff])",
        text,
    ):

        pos = m.start()

        end = m.end()


        if not any(
            s < end
            and pos < e
            for s, e
            in used_ranges
        ):

            matches.append(
                (
                    pos,
                    end,
                    m.group(1),
                )
            )

            used_ranges.append(
                (
                    pos,
                    end,
                )
            )


    if not matches:

        return ""


    matches.sort(
        key=lambda x: x[0]
    )


    chars = []


    for _, _, c in matches:

        if (
            not chars
            or chars[-1] != c
        ):

            chars.append(c)


    return "".join(
        chars[:3]
    )


# ==========================================================
# 強制繁體與辨識修正
# ==========================================================

def force_traditional(
    text,
):

    # ------------------------------------------------------
    # 單音節 A / B / C
    # ------------------------------------------------------

    t_clean = re.sub(
        r"[^\w\u4e00-\u9fa5A-Za-z]",
        "",
        text,
    ).upper()


    if t_clean in [
        "並",
        "逼",
        "B",
    ]:

        return "B方案"


    if t_clean in [
        "C",
        "西",
        "吸",
        "思",
        "四",
    ]:

        return "C方案"


    if t_clean in [
        "A",
        "ㄟ",
    ]:

        return "A方案"


    # ------------------------------------------------------
    # 清除 Whisper 幽靈內容
    # ------------------------------------------------------

    junk_list = [

        "谢谢大家",
        "謝謝大家",

        "WILL ",
        "WILL",

        "請不吝",

        "点赞",
        "點讚",

        "订阅",
        "訂閱",

        "转发",
        "轉發",

        "打赏",
        "明镜",
        "点点栏目",
        "頻道",
        "打開小鈴鐺",

        "YiXi.tv",
        "Yixi",
    ]


    for j in junk_list:

        text = text.replace(
            j,
            "",
        )


    # ------------------------------------------------------
    # 錯字修正
    # ------------------------------------------------------

    mapping = {

        "头": "頭",
        "脑": "腦",
        "维": "維",
        "医": "醫",
        "询": "詢",
        "号": "號",
        "点": "點",

        "復步": "腹部",
        "腹步": "腹部",
        "副部": "腹部",
        "複部": "腹部",

        "功昌": "弓長",
        "公藏": "弓長",
        "公常": "弓長",

        "顏布": "嚴部",
        "嚴步": "嚴部",

        "含怡弄孫": "含飴弄孫",
        "含疑弄孫": "含飴弄孫",

        "的怡": "的貽",
        "的疑": "的貽",

        "耳中城": "耳東陳",
        "耳東城": "耳東陳",

        "成一安": "陳義安",
        "陳義安": "陳奕安",

        "挖一": "我要A",

        "ㄟ": "A",

        "A個": "一個",

        "A方": "A方案",

        "逼方案": "B方案",
        "低方案": "B方案",
        "B方": "B方案",
        "逼方": "B方案",

        "逼上岸": "B方案",

        "第1方案": "B方案",
        "第一方案": "B方案",

        "第1方": "B方案",
        "第一方": "B方案",

        "地方案": "B方案",

        "西方案": "C方案",
        "吸方案": "C方案",
        "思方案": "C方案",
        "四方案": "C方案",

        "斯方案": "C方案",
        "似方案": "C方案",
        "詞方案": "C方案",
        "次方案": "C方案",

        "測方案": "C方案",
        "冊方案": "C方案",
        "策方案": "C方案",
        "側方案": "C方案",

        "私方案": "C方案",
        "司方案": "C方案",
        "絲方案": "C方案",
        "撕方案": "C方案",

        "嗯方案": "C方案",
        "森方案": "C方案",

        "4分之1": "C方案",
        "四分之一": "C方案",
        "四分之": "C方案",

        "的方案C": "C方案",
        "ung方案": "C方案",

        "西方": "C方案",
        "吸方": "C方案",
        "C方": "C方案",
        "C方按": "C方案",

        "我要西": "我要C",
        "我要思": "我要C",
        "我要四": "我要C",
        "我要吸": "我要C",

        "選西": "選C",
        "選思": "選C",
        "選四": "選C",

        "做西": "做C",
        "做思": "做C",
        "做四": "做C",

        "骨密方案": "C方案",
        "骨密度方案": "C方案",
        "肌少方案": "C方案",

        "口天無": "口天吳",
        "銳制": "睿智",

        "方案案": "方案",

        "英文字母一": "E",
        "英文字母1": "E",
        "英文字母E": "E",

        "字母一": "E",

        "英文字母依": "E",
        "英文字母伊": "E",

        "依字開頭": "E",
        "伊字開頭": "E",

        "依開頭": "E",

        "英文E": "E",
        "大寫E": "E",
        "英文的E": "E",

        "上1部": "上一步",
        "上一部": "上一步",
        "上1步": "上一步",
        "上1題": "上一步",

        "退回1步": "退回上一步",
    }


    for k, v in mapping.items():

        text = text.replace(
            k,
            v,
        )


    return text


# ==========================================================
# 身分證模糊修正
# ==========================================================

def solve_id_ambiguity(
    raw_pid: str,
) -> str:

    raw_pid = re.sub(
        r"[^A-Z0-9]",
        "",
        raw_pid.upper(),
    )


    if (
        len(raw_pid) == 10
        and raw_pid[0].isdigit()
    ):

        if raw_pid[0] == "1":

            raw_pid = (
                "E"
                + raw_pid[1:]
            )


    elif (
        len(raw_pid) == 9
        and raw_pid[0].isdigit()
    ):

        raw_pid = (
            "E"
            + raw_pid
        )


    return raw_pid


# ==========================================================
# AI 智慧解析
# ==========================================================

def extract_intelligent_logic(
    text: str,
    current_name: str = "",
):

    try:

        text_trad = (
            force_traditional(
                text
            )
        )


        db_name = (
            resolve_name_from_db(
                text_trad
            )
        )


        num_map = {

            "一": "1",
            "二": "2",
            "兩": "2",

            "三": "3",
            "四": "4",
            "五": "5",

            "六": "6",
            "七": "7",
            "八": "8",

            "九": "9",

            "零": "0",
            "〇": "0",
        }


        for k, v in num_map.items():

            text_trad = (
                text_trad.replace(
                    k,
                    v,
                )
            )


        text_trad = (
            text_trad
            .replace(
                "依",
                "E",
            )
            .replace(
                "伊",
                "E",
            )
        )


        clean_up = (
            text_trad
            .upper()
            .replace(
                " ",
                "",
            )
        )


        id_phone_clean = re.sub(
            r"[^A-Z0-9]",
            "",
            clean_up,
        )


        # --------------------------------------------------
        # AI Prompt
        # --------------------------------------------------

        prompt = f"""
【背景】目前記錄姓名：「{current_name}」
【本地拆字結果】：「{db_name}」（非空時請直接採用，不要更動）
【使用者語音】：「{text_trad}」

規則：

1. intent：
明確要修改 → "correction"
其餘 → "info_provide"

2. extracted_name：
從語音提取姓名（去掉「我叫/我是/名字是」），
最多 3 個繁體中文字，
無法確定留 ""

3. extracted_birthday：
將出生年月日統一轉換為：
「民國年(2-3碼)+月份(2碼)+日期(2碼)」

範例：
「45年2月2號」→ "450202"
「西元1956年1月1日」→ "450101"
「104年11月5號」→ "1041105"

如果無法辨識完整年月日，留 ""

4. extracted_pid：
身分證號，
第一碼「依/伊/E」音 → 大寫 E。

請完全忠於使用者原字串，
不可自行新增、修改或補齊數字。

無法確定留 ""。

嚴禁簡體字。

回傳純 JSON：

{{
    "intent": "...",
    "extracted_name": "...",
    "extracted_birthday": "...",
    "extracted_pid": "..."
}}
"""


        # --------------------------------------------------
        # 呼叫 Groq
        # --------------------------------------------------

        try:

            if client is None:

                raise RuntimeError(
                    "Groq client 尚未初始化"
                )


            response = (
                client
                .chat
                .completions
                .create(
                    model="openai/gpt-oss-120b",
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    response_format={
                        "type":
                            "json_object"
                    },
                    temperature=0.0,
                )
            )


            res = json.loads(
                response
                .choices[0]
                .message
                .content
            )


        except Exception as e:

            print(
                "AI parse fallback:",
                repr(e),
            )


            res = {

                "intent":
                    "info_provide",

                "extracted_name":
                    db_name,

                "extracted_birthday":
                    "",

                "extracted_pid":
                    "",
            }


        # --------------------------------------------------
        # A / B / C 方案
        # --------------------------------------------------

        plan = ""


        if (
            re.search(
                r"(^A$|A方案|方案A|我要A|選A|做A|腦肺)",
                clean_up,
            )
            or any(
                k in clean_up
                for k in [

                    "腦",
                    "頭",
                    "維他",
                    "B12",
                    "葉酸",

                    "X光",
                    "暈",
                    "咳",
                    "喘",

                    "記憶",
                    "忘",
                    "心悸",
                ]
            )
        ):

            plan = "A"


        elif (
            re.search(
                r"(^B$|B方案|方案B|我要B|選B|做B|腹部)",
                clean_up,
            )
            or any(
                k in clean_up
                for k in [

                    "腹",
                    "胃",
                    "腸",

                    "糖",

                    "超音波",

                    "消化",

                    "胖",
                    "渴",

                    "肝",
                    "膽",
                    "腎",
                ]
            )
        ):

            plan = "B"


        elif (
            re.search(
                r"(^C$|C方案|方案C|我要C|選C|做C|骨密)",
                clean_up,
            )
            or any(
                k in clean_up
                for k in [

                    "骨",
                    "肌",

                    "無力",
                    "沒力",

                    "跌倒",

                    "痠",
                    "痛",

                    "走不動",
                    "站不住",

                    "腳",
                    "關節",
                ]
            )
        ):

            plan = "C"


        elif any(
            k in clean_up
            for k in [
                "尿",
                "血",
                "諮詢",
                "醫師",
            ]
        ):

            plan = "COMMON"


        # --------------------------------------------------
        # 身分證
        # --------------------------------------------------

        pid = ""


        ai_pid = re.sub(
            r"[^A-Z0-9]",
            "",
            res
            .get(
                "extracted_pid",
                "",
            )
            .upper(),
        )


        ai_digits = re.sub(
            r"\D",
            "",
            ai_pid,
        )


        raw_digits = re.sub(
            r"\D",
            "",
            id_phone_clean,
        )


        if (
            ai_digits
            and (
                ai_digits
                in raw_digits
            )
        ):

            pid = (
                solve_id_ambiguity(
                    ai_pid
                )
            )


        else:

            m = re.search(
                r"[A-Z]?\d{8,10}",
                id_phone_clean,
            )


            if m:

                pid = (
                    solve_id_ambiguity(
                        m.group(0)
                    )
                )


        if pid:

            text_trad = re.sub(
                r"[A-Za-z1]?\d{9}",
                pid,
                text_trad,
                count=1,
                flags=re.IGNORECASE,
            )


        # --------------------------------------------------
        # 手機號碼
        # --------------------------------------------------

        phone = ""


        phone_source = re.sub(
            r"[\s\-]",
            "",
            text_trad,
        )


        pm = re.search(
            r"09\d{8}",
            phone_source,
        )


        if pm:

            candidate = (
                pm.group(0)
            )


            if (
                len(candidate)
                == 10
                and candidate.startswith(
                    "09"
                )
            ):

                phone = candidate


        # --------------------------------------------------
        # 姓名
        # --------------------------------------------------

        final_name = (
            db_name
            if db_name
            else res.get(
                "extracted_name",
                "",
            )
        )


        if final_name:

            final_name = re.sub(
                r"[^\u4e00-\u9fa5]",
                "",
                final_name,
            )


            for rm in [
                "我叫",
                "我是",
                "名字是",
            ]:

                final_name = (
                    final_name.replace(
                        rm,
                        "",
                    )
                )


            final_name = (
                final_name.strip()
            )


            if final_name.endswith(
                "的"
            ):

                final_name = ""


            elif (
                len(final_name)
                > 3
            ):

                final_name = (
                    final_name[:3]
                )


        # --------------------------------------------------
        # 出生年月日
        # --------------------------------------------------

        birthday = res.get(
            "extracted_birthday",
            "",
        )


        if birthday:

            bs = re.sub(
                r"\D",
                "",
                str(
                    birthday
                ),
            )


            if (
                5
                <= len(bs)
                <= 7
            ):

                try:

                    mm = int(
                        bs[-4:-2]
                    )

                    dd = int(
                        bs[-2:]
                    )


                    birthday = (
                        bs
                        if (
                            1 <= mm <= 12
                            and
                            1 <= dd <= 31
                        )
                        else ""
                    )


                except Exception:

                    birthday = ""


            else:

                birthday = ""


        # --------------------------------------------------
        # 回傳結果
        # --------------------------------------------------

        data = {

            "intent":
                res.get(
                    "intent",
                    "info_provide",
                ),

            "name":
                final_name,

            "birthday":
                birthday,

            "plan":
                plan,

            "pid":
                pid,

            "phone":
                phone,
        }


        return {

            "status":
                "success",

            "result": {

                "translated_text":
                    text_trad,

                "data":
                    data,
            },
        }


    except Exception as e:

        return {

            "status":
                "error",

            "result":
                {},

            "debug":
                str(e),
        }


# ==========================================================
# Smart Parse
# ==========================================================

class ExtractRequest(
    BaseModel
):

    text: str

    current_name: str = ""


@app.post(
    "/api/smart_parse"
)
def smart_parse(
    req: ExtractRequest,
):

    return (
        extract_intelligent_logic(
            req.text,
            req.current_name,
        )
    )


# ==========================================================
# AI Voice Booking
# ==========================================================

class VoiceBookingRequest(
    BaseModel
):

    text: str


@app.post(
    "/api/ai_voice_booking"
)
def ai_voice_booking(
    req: VoiceBookingRequest,
):

    result = (
        extract_intelligent_logic(
            req.text
        )
    )


    data = (
        result
        .get(
            "result",
            {},
        )
        .get(
            "data",
            {},
        )
    )


    missing = []


    if not data.get(
        "name"
    ):

        missing.append(
            "姓名"
        )


    if not data.get(
        "pid"
    ):

        missing.append(
            "身分證號碼"
        )


    if not data.get(
        "plan"
    ):

        missing.append(
            "健檢方案"
        )


    if missing:

        return {

            "status":
                "error",

            "message":
                "以下資料未能辨識，請重新說明："
                + "、".join(
                    missing
                ),

            "data":
                data,
        }


    return {

        "status":
            "success",

        "message":
            "資料解析成功",

        "data":
            data,
    }


# ==========================================================
# Whisper Booking
# ==========================================================

@app.post(
    "/api/whisper_booking"
)
async def whisper_booking(

    file: UploadFile = File(...),

    current_name: str = Form(""),

):

    if client is None:

        return {

            "status":
                "error",

            "message":
                "尚未設定 GROQ_API_KEY；"
                "文字輸入與自費價格查詢仍可使用。",
        }


    temp = os.path.join(
        BASE_DIR,
        f"temp_{os.path.basename(file.filename or 'audio.webm')}",
    )


    with open(
        temp,
        "wb",
    ) as f:

        f.write(
            await file.read()
        )


    try:

        with open(
            temp,
            "rb",
        ) as af:

            trans = (
                client
                .audio
                .transcriptions
                .create(
                    file=af,

                    model=
                        "whisper-large-v3",

                    language=
                        "zh",

                    prompt=(
                        "這是一段台灣醫療健檢預約的對話。"
                        "常見詞彙包含："
                        "A方案、B方案、C方案、"
                        "腦肺、腹部、骨密肌力、"
                        "身分證字號、民國、出生年月日。"
                        "請絕對使用繁體中文輸出，"
                        "嚴禁簡體字與外文。"
                    ),
                )
            )


        raw = trans.text


        if is_hallucination(
            raw
        ):

            return {

                "status":
                    "success",

                "raw_text":
                    "",

                "result": {

                    "data":
                        {},
                },
            }


        return {

            "status":
                "success",

            "raw_text":
                raw,

            "result":
                extract_intelligent_logic(
                    raw,
                    current_name,
                ).get(
                    "result",
                    {},
                ),
        }


    except Exception:
        # 除錯用：保留失敗的音檔，方便檢查內容
        if os.path.exists(temp):
            debug_path = os.path.join(BASE_DIR, f"debug_{os.path.basename(temp)}")
            os.rename(temp, debug_path)
            print(f"[DEBUG] 失敗音檔已保留：{debug_path}")
        raise
    finally:
        if os.path.exists(temp):
            os.remove(temp)


# ==========================================================
# ★ 老人健檢 + 自費項目 最終預約 API
# ==========================================================

class BookingConfirmRequest(
    BaseModel
):

    plan: str = ""

    planName: str = ""

    name: str = ""

    birthday: str = ""

    pid: str = ""

    phone: str = ""

    date: str = ""

    time: str = ""

    selfPayDate: str = ""

    selfPayTime: str = ""

    breakfast: (
        str
        | int
        | None
    ) = None

    captcha: (
        str
        | None
    ) = None


    selfPayItems: list[
        dict[
            str,
            Any,
        ]
    ] = Field(
        default_factory=list
    )


    selfPayTotal: (
        int
        | float
    ) = 0


# ==========================================================
# POST /api/booking/confirm
# ==========================================================

@app.post(
    "/api/booking/confirm"
)
async def confirm_booking(
    req: BookingConfirmRequest,
):

    try:

        # --------------------------------------------------
        # 基本欄位檢查
        # --------------------------------------------------

        if not req.name.strip():

            raise HTTPException(
                status_code=400,
                detail="姓名不可空白",
            )


        if not req.pid.strip():

            raise HTTPException(
                status_code=400,
                detail="身分證字號不可空白",
            )


        if not req.phone.strip():

            raise HTTPException(
                status_code=400,
                detail="手機號碼不可空白",
            )


        # --------------------------------------------------
        # 後端重新計算一次自費總額
        #
        # 不完全相信前端傳進來的 selfPayTotal。
        # --------------------------------------------------

        server_total = 0


        cleaned_self_pay_items = []


        for item in req.selfPayItems:

            clean_item = dict(
                item
            )


            raw_price = (
                clean_item.get(
                    "price"
                )
            )


            price = None


            if raw_price not in (
                None,
                "",
            ):

                try:

                    price = float(
                        raw_price
                    )


                    if (
                        price.is_integer()
                    ):

                        price = int(
                            price
                        )


                    server_total += (
                        float(
                            price
                        )
                    )


                except (
                    TypeError,
                    ValueError,
                ):

                    price = None


            clean_item[
                "price"
            ] = price


            cleaned_self_pay_items.append(
                clean_item
            )


        if float(
            server_total
        ).is_integer():

            server_total = int(
                server_total
            )


        # --------------------------------------------------
        # 建立最終預約資料
        # --------------------------------------------------

        booking_record = {

            "plan":
                req.plan,

            "plan_name":
                req.planName,

            "name":
                req.name,

            "birthday":
                req.birthday,

            "pid":
                req.pid,

            "phone":
                req.phone,

            "date":
                req.date,

            "time":
                req.time,

            "self_pay_date":
                req.selfPayDate,

            "self_pay_time":
                req.selfPayTime,

            "breakfast":
                req.breakfast,

            "captcha":
                req.captcha,

            "self_pay_items":
                cleaned_self_pay_items,

            "self_pay_count":
                len(
                    cleaned_self_pay_items
                ),

            "self_pay_total":
                server_total,
        }


        # --------------------------------------------------
        # Terminal 顯示
        # --------------------------------------------------

        print()
        print("=" * 70)

        print(
            "收到老人健檢最終預約"
        )

        print("-" * 70)


        print(
            json.dumps(
                booking_record,
                ensure_ascii=False,
                indent=2,
            )
        )


        print("=" * 70)
        print()
        # --------------------------------------------------
        # 寫入 Firebase
        # --------------------------------------------------
        try:
            if init_firebase():

                firebase_key = (
                    req.pid.strip().upper()
                    if req.pid.strip()
                    else f"WEB_{req.phone.strip()}"
                )

                # ==========================================
                # 純自費預約
                # ==========================================
                if req.plan == "SELF_PAY":

                    firebase_record = {
                        "name": req.name.strip(),
                        "phone": req.phone.strip(),
                        "birth": req.birthday.strip(),
                        "idNumber": req.pid.strip().upper(),
                        "selfPayDate": req.selfPayDate.strip(),
                        "selfPayTime": req.selfPayTime.strip(),
                        "selfPayItems": cleaned_self_pay_items,
                        "selfPayCount": len(cleaned_self_pay_items),
                        "selfPayTotal": server_total,
                        "bookedAt": datetime.now().isoformat(),
                        "source": "SELF_PAY_BOOKING",
                    }

                    db.reference(
                        f"self_pay_booking/{firebase_key}"
                    ).update(firebase_record)

                    print(
                        f"Firebase 寫入成功：self_pay_booking/{firebase_key}"
                    )

                    return {
                        "status": "success",
                        "message": "自費健檢預約已成功接收",
                        "booking": firebase_record,
                        "selfPayCount": len(cleaned_self_pay_items),
                        "selfPayTotal": server_total,
                    }

                # ==========================================
                # 老人健檢 A / B / C
                # ==========================================
                plan_value = str(
                    req.plan or ""
                ).strip().upper()

                if plan_value not in ("A", "B", "C"):
                    raise HTTPException(
                        status_code=400,
                        detail="老人健檢方案只能是 A、B 或 C",
                    )

                veg_value = str(
                    req.breakfast or ""
                ).strip()

                if veg_value == "1":
                    veg_value = "葷"
                elif veg_value == "2":
                    veg_value = "素"
                elif veg_value in ("葷", "葷食"):
                    veg_value = "葷"
                elif veg_value in ("素", "素食"):
                    veg_value = "素"

                firebase_record = {
                    "name": req.name.strip(),
                    "phone": req.phone.strip(),
                    "plan": plan_value,
                    "date": req.date.strip(),
                    "time": req.time.strip(),
                    "bookedAt": datetime.now().isoformat(),
                    "source": "WEB_BOOKING",
                    "birth": req.birthday.strip(),
                    "idNumber": req.pid.strip().upper(),
                    "veg": veg_value,
                }
                # 老人健檢 + 自費加購
                if (
                    cleaned_self_pay_items
                    or req.selfPayDate.strip()
                    or req.selfPayTime.strip()
                ):
                    firebase_record.update({
                        "selfPayDate": req.selfPayDate.strip(),
                        "selfPayTime": req.selfPayTime.strip(),
                        "selfPayItems": cleaned_self_pay_items,
                        "selfPayCount": len(cleaned_self_pay_items),
                        "selfPayTotal": server_total,
                    })

                # 沒有自費時，清除同一身分證舊的自費欄位
                else:
                    firebase_record.update({
                        "selfPayDate": None,
                        "selfPayTime": None,
                        "selfPayItems": None,
                        "selfPayCount": None,
                        "selfPayTotal": None,
                    })

                print(
                    f"準備寫入 Firebase：appointments/{firebase_key}"
                )

                db.reference(
                    f"appointments/{firebase_key}"
                ).update(firebase_record)

                print(
                    f"Firebase 寫入成功：appointments/{firebase_key}"
                )

            else:
                print(
                    "Firebase 未初始化，跳過寫入。"
                )

        except HTTPException:
            raise

        except Exception as fe:
            print(
                "Firebase 寫入失敗：",
                repr(fe)
            )
            raise HTTPException(
                status_code=500,
                detail="Firebase 寫入失敗",
            )
        # --------------------------------------------------
        # 成功
        # --------------------------------------------------
        return {
            "status":
                "success",

            "message":
                "老人健檢與自費項目資料已成功接收",

            "booking":
                booking_record,

            "selfPayCount":
                len(
                    cleaned_self_pay_items
                ),

            "selfPayTotal":
                server_total,
        }


    except HTTPException:

        raise


    except Exception as e:

        print(
            "confirm_booking error:",
            repr(e),
        )


        raise HTTPException(
            status_code=500,
            detail=(
                "預約資料處理失敗："
                + str(e)
            ),
        )


# ==========================================================
# ==========================================================
# Firebase Test Write
# ==========================================================
@app.get("/api/firebase/test-write")
def firebase_test_write():
    ok = init_firebase()

    if not ok:
        return {
            "success": False,
            "message": "Firebase not initialized."
        }

    test_key = "TEST_WEB_001"

    record = {
        "name": "測試姓名",
        "phone": "0912345678",
        "plan": "B",
        "date": "2026-05-01",
        "time": "09:00",
        "bookedAt": datetime.now().isoformat(),
        "source": "WEB_TEST",
        "birth": "1950-01-01",
        "idNumber": test_key,
        "veg": "葷"
    }

    db.reference(f"appointments/{test_key}").update(record)

    return {
        "success": True,
        "message": "Firebase test write success.",
        "key": test_key,
        "record": record
    }

# Health Check
# ==========================================================

@app.get(
    "/api/booking/health"
)
def booking_health():

    return {

        "status":
            "success",

        "message":
            "Booking API is running",

        "groq_loaded":
            bool(
                GROQ_API_KEY
            ),
    }


# ==========================================================
# 啟動 Server
# ==========================================================

if __name__ == "__main__":

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
    )