from playwright.sync_api import sync_playwright
import time

def run_scheme_c_test():
    # 測試假資料，這次我們測 C 方案
    test_user = {
        "plan": "C",             # 這裡改成 C
        "name": "陳大勇",
        "birthday": "480101",
        "pid": "A123456789",
        "phone": "0911222333",
        "time": "11:30",
        "breakfast": "2" 
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print(f"🎬 正在測試 {test_user['plan']} 方案自動化...")
        page.goto(f"https://shop.jotangi.net/ShanLinHC/appointment2.html?p={test_user['plan']}")

        # 填寫資料
        page.locator('#member_name').fill(test_user['name'])
        page.locator('#member_birthday').fill(test_user['birthday'])
        page.locator('#member_pid').fill(test_user['pid'])
        page.locator('#member_phone').fill(test_user['phone'])

        # 自動選第一個可約日期
        page.wait_for_function('document.querySelector("#reserve_date").options.length > 1')
        page.locator('#reserve_date').select_option(index=1)
        page.locator('#reserve_time').select_option(value=test_user['time'])

        # 早餐與驗證碼
        if test_user['breakfast'] == "2": page.locator('#breakfast2').click()
        ans = page.locator('#ans').input_value()
        page.locator('#val2').fill(ans)

        print("🎉 C 方案測試填表成功！")
        time.sleep(10)
        browser.close()

if __name__ == "__main__":
    run_scheme_c_test()


