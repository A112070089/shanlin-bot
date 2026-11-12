import uvicorn
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
from self_pay_api import router as self_pay_router
import json, os, re

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(self_pay_router)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1") if (GROQ_API_KEY and OpenAI) else None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "database.json")
with open(DB_PATH, encoding="utf-8") as _f:
    _DB = json.load(_f)
NAME_DB = _DB["NAME_DB"]   

HALLUCINATION_EXACT = {"謝謝","謝謝收看","謝謝觀看","請訂閱","感謝收聽",
                        ".","。","，"," ","　"}
HALLUCINATION_CONTAINS = [
    "谢谢大家","謝謝大家","WILL ","點讚","訂閱","轉發",
    "明镜","頻道","打開小鈴鐺","MING PAO","CANADA","TORONTO",
    "澳洲","加拿大","報紙","DANGER","AMARA","SUBTITLE",
    "谢谢","点赞","订阅","转发","YIXI.TV","YIXI" # 🌟 封殺 YiXi 幽靈
]

def is_hallucination(text: str) -> bool:
    t = text.strip()
    if not t or t in HALLUCINATION_EXACT:
        return True
    for h in HALLUCINATION_CONTAINS:
        if h in t.upper():
            return True
    if re.search(r'[\u3040-\u30FF]', t):  
        return True
    if len(re.sub(r'[^\w]', '', t)) == 0:
        return True
    return False

def resolve_name_from_db(text: str) -> str:
    if not text:
        return ""
    matches = []
    used_ranges = []
    sorted_keys = sorted(NAME_DB.keys(), key=len, reverse=True)
    for key in sorted_keys:
        idx = 0
        while True:
            pos = text.find(key, idx)
            if pos == -1: break
            end = pos + len(key)
            if not any(s < end and pos < e for s, e in used_ranges):
                matches.append((pos, end, NAME_DB[key]))
                used_ranges.append((pos, end))
            idx = pos + 1

    for m in re.finditer(r'[\u4e00-\u9fff]{1,8}的([\u4e00-\u9fff])', text):
        pos, end = m.start(), m.end()
        if not any(s < end and pos < e for s, e in used_ranges):
            matches.append((pos, end, m.group(1)))
            used_ranges.append((pos, end))

    if not matches: return ""
    matches.sort(key=lambda x: x[0])
    chars = []
    for _, _, c in matches:
        if not chars or chars[-1] != c: chars.append(c)
    return "".join(chars[:3])   

def force_traditional(text):
    # ✅ 1. 處理單音節的極端狀況：如果整句話清掉標點符號後只有一個字或一個音
    t_clean = re.sub(r'[^\w\u4e00-\u9fa5A-Za-z]', '', text).upper()
    if t_clean in ["並", "逼", "B"]: return "B方案"
    if t_clean in ["C", "西", "吸", "思", "四"]: return "C方案"
    if t_clean in ["A", "ㄟ"]: return "A方案"

    # 2. 清除幽靈幻覺字
    junk_list = ["谢谢大家","謝謝大家","WILL ","WILL","請不吝","点赞","點讚",
                 "订阅","訂閱","转发","轉發","打赏","明镜","点点栏目","頻道","打開小鈴鐺", "YiXi.tv", "Yixi"]
    for j in junk_list: text = text.replace(j, "")
    
    # 3. 錯字與視覺美化替換字典
    mapping = {
        "头":"頭","脑":"腦","维":"維","医":"醫","询":"詢","号":"號","点":"點",
        "復步":"腹部","腹步":"腹部","副部":"腹部","複部":"腹部",
        "功昌":"弓長","公藏":"弓長","公常":"弓長","顏布":"嚴部","嚴步":"嚴部",
        "含怡弄孫":"含飴弄孫","含疑弄孫":"含飴弄孫","的怡":"的貽","的疑":"的貽",
        "耳中城":"耳東陳","耳東城":"耳東陳","成一安":"陳義安","陳義安":"陳奕安",
        "挖一":"我要A","ㄟ":"A","A個":"一個","A方":"A方案",
        "逼方案":"B方案","低方案":"B方案","B方":"B方案","逼方":"B方案",
        "逼上岸":"B方案","第1方案": "B方案","第一方案": "B方案","第1方": "B方案",
        "第一方": "B方案","地方案": "B方案",
        "西方案":"C方案","吸方案":"C方案","思方案":"C方案","四方案":"C方案",
        "斯方案":"C方案","似方案":"C方案","詞方案":"C方案","次方案":"C方案",
        "測方案":"C方案","冊方案":"C方案","策方案":"C方案","側方案":"C方案",
        "私方案":"C方案","司方案":"C方案","絲方案":"C方案","撕方案":"C方案",
        "嗯方案":"C方案","森方案":"C方案",
        "4分之1":"C方案","四分之一":"C方案","四分之":"C方案",
        "的方案C":"C方案","ung方案":"C方案",
        "西方":"C方案","吸方":"C方案","C方":"C方案","C方按":"C方案",
        "我要西":"我要C","我要思":"我要C","我要四":"我要C","我要吸":"我要C",
        "選西":"選C","選思":"選C","選四":"選C",
        "做西":"做C","做思":"做C","做四":"做C",
        "骨密方案":"C方案","骨密度方案":"C方案","肌少方案":"C方案",
        "口天無":"口天吳","銳制":"睿智",
        "方案案":"方案",
        "英文字母一":"E","英文字母1":"E","英文字母E":"E","字母一":"E",
        "英文字母依":"E","英文字母伊":"E","依字開頭":"E","伊字開頭":"E","依開頭":"E",
        "英文E":"E","大寫E":"E","英文的E":"E",
        
        # ✅ 4. 視覺美化：把醜醜的語音辨識結果換成漂亮的格式，讓氣泡看起來舒服
        "上1部":"上一步",
        "上一部":"上一步",
        "上1步":"上一步",
        "上1題":"上一步",
        "退回1步":"退回上一步"
    }
    
    for k, v in mapping.items(): text = text.replace(k, v)
    return text

def solve_id_ambiguity(raw_pid: str) -> str:
    raw_pid = re.sub(r'[^A-Z0-9]', '', raw_pid.upper())
    if len(raw_pid) == 10 and raw_pid[0].isdigit():
        if raw_pid[0] == "1": raw_pid = "E" + raw_pid[1:]
    elif len(raw_pid) == 9 and raw_pid[0].isdigit():
        raw_pid = "E" + raw_pid
    return raw_pid

def extract_intelligent_logic(text: str, current_name: str = ""):
    try:
        text_trad = force_traditional(text)
        db_name = resolve_name_from_db(text_trad)

        num_map = {"一":"1","二":"2","兩":"2","三":"3","四":"4","五":"5",
                   "六":"6","七":"7","八":"8","九":"9","零":"0","〇":"0"}
        for k, v in num_map.items(): text_trad = text_trad.replace(k, v)
        text_trad = text_trad.replace("依","E").replace("伊","E")

        # 必須先定義這兩個，下面才抓得到
        clean_up = text_trad.upper().replace(" ", "")
        id_phone_clean = re.sub(r'[^A-Z0-9]', '', clean_up)

        # ⚠️ 這裡是你原本不小心刪掉的 prompt，我幫你補回來了
        prompt = f"""
【背景】目前記錄姓名：「{current_name}」
【本地拆字結果】：「{db_name}」（非空時請直接採用，不要更動）
【使用者語音】：「{text_trad}」

規則：
1. intent：明確要修改 → "correction"；其餘 → "info_provide"
2. extracted_name：從語音提取姓名（去掉「我叫/我是/名字是」），最多 3 個繁體中文字，無法確定留 ""
3. extracted_birthday：將出生年月日統一轉換為「民國年(2-3碼)+月份(2碼)+日期(2碼)」的純數字字串。
   - 範例1：「45年2月2號」→ "450202" (個位數自動補零)
   - 範例2：「西元1956年1月1日」→ "450101" (自動將西元轉民國)
   - 範例3：「104年11月5號」→ "1041105"
   如果無法辨識出完整年月日，請留 ""。
4. extracted_pid：身分證號，第一碼「依/伊/E」音 → 輸出大寫 E。⚠️請【完全忠於使用者原字串】提取，絕對不可自行新增、修改或補齊數字！無法確定留 ""
🚨 嚴禁簡體字！

回傳純 JSON（無 markdown）：
{{"intent":"...","extracted_name":"...","extracted_birthday":"...","extracted_pid":"..."}}
"""
        
        # 呼叫 AI 必須在最前面，才能拿到 res
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            res = json.loads(response.choices[0].message.content)
        except:
            res = {"intent":"info_provide","extracted_name":db_name,
                   "extracted_birthday":"","extracted_pid":""}

        plan = ""
        if re.search(r'(^A$|A方案|方案A|我要A|選A|做A|腦肺)', clean_up) or any(k in clean_up for k in ["腦","頭","維他","B12","葉酸","X光","暈","咳","喘","記憶","忘","心悸"]): plan = "A"
        elif re.search(r'(^B$|B方案|方案B|我要B|選B|做B|腹部)', clean_up) or any(k in clean_up for k in ["腹","胃","腸","糖","超音波","消化","胖","渴","肝","膽","腎"]): plan = "B"
        elif re.search(r'(^C$|C方案|方案C|我要C|選C|做C|骨密)', clean_up) or any(k in clean_up for k in ["骨","肌","無力","沒力","跌倒","痠","痛","走不動","站不住","腳","關節"]): plan = "C"
        elif any(k in clean_up for k in ["尿","血","諮詢","醫師"]): plan = "COMMON"

        pid = ""
        ai_pid = re.sub(r'[^A-Z0-9]', '', res.get("extracted_pid","").upper())
        
        # --- 🛡️ 防腦補強制驗證機制 (必須放在拿到 res 之後) ---
        ai_digits = re.sub(r'\D', '', ai_pid)
        raw_digits = re.sub(r'\D', '', id_phone_clean)

        if ai_digits and (ai_digits in raw_digits):
            pid = solve_id_ambiguity(ai_pid)
        else:
            # LLM 腦補了！拋棄 AI 結果，用正則直接從原句抓 (容忍 8~10 碼錯誤長度)
            m = re.search(r'[A-Z]?\d{8,10}', id_phone_clean)
            if m: 
                pid = solve_id_ambiguity(m.group(0))

        if pid: text_trad = re.sub(r'[A-Za-z1]?\d{9}', pid, text_trad, count=1, flags=re.IGNORECASE)

        # 抓手機號碼
        phone = ""
        phone_source = re.sub(r'[\s\-]', '', text_trad)  
        pm = re.search(r'09\d{8}', phone_source)
        if pm:
            candidate = pm.group(0)
            if len(candidate) == 10 and candidate.startswith("09"):
                phone = candidate

        final_name = db_name if db_name else res.get("extracted_name","")
        if final_name:
            final_name = re.sub(r'[^\u4e00-\u9fa5]', '', final_name)
            for rm in ["我叫","我是","名字是"]: final_name = final_name.replace(rm, "")
            final_name = final_name.strip()
            if final_name.endswith("的"): final_name = ""
            elif len(final_name) > 3: final_name = final_name[:3]

        birthday = res.get("extracted_birthday","")
        if birthday:
            bs = re.sub(r'\D','',str(birthday))
            if 5 <= len(bs) <= 7:
                try:
                    mm, dd = int(bs[-4:-2]), int(bs[-2:])
                    birthday = bs if (1<=mm<=12 and 1<=dd<=31) else ""
                except: birthday = ""
            else: birthday = ""

        data = {
            "intent":   res.get("intent","info_provide"),
            "name":     final_name,
            "birthday": birthday,
            "plan":     plan,
            "pid":      pid,
            "phone":    phone,
        }
        return {"status":"success","result":{"translated_text":text_trad,"data":data}}
    except Exception as e:
        return {"status":"error","result":{},"debug":str(e)}

class ExtractRequest(BaseModel):
    text: str
    current_name: str = ""

@app.post("/api/smart_parse")
def smart_parse(req: ExtractRequest):
    return extract_intelligent_logic(req.text, req.current_name)

class VoiceBookingRequest(BaseModel):
    text: str

@app.post("/api/ai_voice_booking")
def ai_voice_booking(req: VoiceBookingRequest):
    result = extract_intelligent_logic(req.text)
    data   = result.get("result",{}).get("data",{})
    missing = []
    if not data.get("name"):  missing.append("姓名")
    if not data.get("pid"):   missing.append("身分證號碼")
    if not data.get("plan"):  missing.append("健檢方案")
    if missing:
        return {"status":"error",
                "message":f"以下資料未能辨識，請重新說明：{'、'.join(missing)}",
                "data":data}
    return {"status":"success","message":"資料解析成功","data":data}

@app.post("/api/whisper_booking")
async def whisper_booking(file: UploadFile = File(...), current_name: str = Form("")):
    if client is None:
        return {"status":"error", "message":"尚未設定 GROQ_API_KEY；文字輸入與自費價格查詢仍可使用。"}
    temp = f"temp_{file.filename}"
    with open(temp,"wb") as f: f.write(await file.read())
    try:
        with open(temp,"rb") as af:
            trans = client.audio.transcriptions.create(
                file=af, model="whisper-large-v3", language="zh",
                # ✅ 加入提示詞 (Prompt Injection)，讓模型知道這段對話的常見詞彙，大幅減少亂碼與誤判
                prompt="這是一段台灣醫療健檢預約的對話。常見詞彙包含：A方案、B方案、C方案、腦肺、腹部、骨密肌力、身分證字號、民國、出生年月日。請絕對使用繁體中文輸出，嚴禁簡體字與外文。"
            )
        raw = trans.text
        if is_hallucination(raw):
            return {"status":"success","raw_text":"","result":{"data":{}}}
        return {"status":"success","raw_text":raw,
                "result":extract_intelligent_logic(raw,current_name).get("result",{})}
    finally:
        if os.path.exists(temp): os.remove(temp)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)