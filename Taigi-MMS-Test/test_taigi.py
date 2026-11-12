
import torch
import soundfile as sf
from transformers import VitsModel, AutoTokenizer

MODEL = "facebook/mms-tts-nan"

print("正在載入台語 AI 模型...")

tokenizer = AutoTokenizer.from_pretrained(MODEL)
model = VitsModel.from_pretrained(
    MODEL,
    use_safetensors=True
)

model.eval()
model.to("cpu")

# 台語羅馬字：你好，謝謝你
text = "Lí hó, to-siā lí."

print("正在合成台語語音...")

inputs = tokenizer(text, return_tensors="pt")

with torch.inference_mode():
    audio = model(**inputs).waveform

waveform = audio.squeeze().cpu().numpy()

sf.write(
    "taigi_test.wav",
    waveform,
    model.config.sampling_rate
)

print("完成！音檔：taigi_test.wav")
