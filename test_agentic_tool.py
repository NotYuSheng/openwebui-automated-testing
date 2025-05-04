from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import pyautogui
import pyperclip
import time

BASE_URL = "http://localhost:8080"


def main():
    options = webdriver.EdgeOptions()
    # options.add_argument("--headless")  # Uncomment for headless mode
    driver = webdriver.Edge(options=options)
    driver.maximize_window()
    wait = WebDriverWait(driver, 30)

    try:
        driver.get(f"{BASE_URL}/auth")

        try:
            email_input = wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[@name='email']"))
            )
            password_input = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//input[@name='current-password']")
                )
            )
            login_button = wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//button[@type='submit' and contains(text(),'Sign in')]",
                    )
                )
            )

            email_input.send_keys("testuser@gmail.com")
            password_input.send_keys("user123")
            login_button.click()
            time.sleep(5)
            
        except Exception as e:
            print(f"❌ Login failed: {e}")
            driver.quit()
            return

        try:
            driver.get("http://localhost:8080/workspace/tools/create")
            time.sleep(2)

            tool_name = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//input[@placeholder='Tool Name']")
                )
            )
            tool_name.send_keys("GetTime")

            tool_desc = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//input[@placeholder='Tool Description']")
                )
            )
            tool_desc.send_keys("Get current time and date")

            time.sleep(1)

            tool_code = """from datetime import datetime
import pytz
from pydantic import BaseModel


class Tools:
    class Valves(BaseModel):
        pass

    class UserValves(BaseModel):
        pass

    def __init__(self):
        self.valves = self.Valves()
        self.user_valves = self.UserValves()

    def get_current_date(self, timezone: str = "Asia/Singapore") -> str:
        \"\"\"Get current date in specified timezone\"\"\"
        tz = pytz.timezone(timezone)
        current_date = datetime.now(tz).strftime("%A, %B %d, %Y")
        return f"Today's date in {timezone} is {current_date}"

    def get_current_time(self, timezone: str = "Asia/Singapore") -> str:
        \"\"\"Get current time in specified timezone\"\"\"
        tz = pytz.timezone(timezone)
        current_time = datetime.now(tz).strftime("%H:%M:%S")
        return f"Current Time in {timezone}: {current_time}"


# Example usage:
tools = Tools()

# 1. Direct call (will use Singapore time by default)
print(tools.get_current_time())  # "Current Time in Asia/Singapore: 14:30:00"

# 2. Native tool calling integration
__tools__ = {
    "get_current_time": {
        "spec": {
            "name": "get_current_time",
            "description": "Get the current time in a specified timezone",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Timezone identifier (e.g., Asia/Singapore)",
                        "default": "Asia/Singapore",
                    }
                },
                "required": [],
            },
        },
        "callable": Tools().get_current_time,
        "file_handler": False,
        "citation": False,
    },
    "get_current_date": {
        "spec": {
            "name": "get_current_date",
            "description": "Get the current date in a specified timezone",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Timezone identifier (e.g., Asia/Singapore)",
                        "default": "Asia/Singapore",
                    }
                },
                "required": [],
            },
        },
        "callable": Tools().get_current_date,
        "file_handler": False,
        "citation": False,
    },
}"""
            pyperclip.copy(tool_code)

            editor = wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "cm-content"))
            )
            editor.click()
            ActionChains(driver).key_down(Keys.CONTROL).send_keys("a").key_up(
                Keys.CONTROL
            ).perform()
            ActionChains(driver).key_down(Keys.CONTROL).send_keys("v").key_up(
                Keys.CONTROL
            ).perform()
            
            # Close popup if exists
            try:
                popup_close = wait.until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(@class, 'shrink-0 pr-1')]//button")
                    )
                )
                if popup_close.is_displayed():
                    popup_close.click()
                    time.sleep(1)
            except:
                print("ℹ️ No update popup found, continuing.")

            # Click Save
            save_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Save')]"))
            )
            save_button.click()

            # Confirm
            confirm_button = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(text(),'Confirm')]")
                )
            )
            confirm_button.click()
            time.sleep(15)

            # Test the tool functionality
            try:
                driver.get(BASE_URL)
                more_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='More']//*[name()='svg']")))
                more_btn.click()

                toggle_tool = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'cursor-pointer') and @role='switch']")))
                toggle_tool.click()

                chat_input = wait.until(EC.presence_of_element_located((By.ID, "chat-input")))
                chat_input.click()
                ActionChains(driver).send_keys("What is the current time?").send_keys(Keys.RETURN).perform()
                time.sleep(30)

                # You might want to add verification for the tool's response here
                # For example:
                try:
                    response = wait.until(
                        EC.presence_of_element_located(
                            (By.XPATH, "//div[contains(text(), 'Current Time in')]")
                        )
                    )
                    print(f"✅ Tool response received: {response.text}")
                except:
                    print("❌ No tool response detected")

            except Exception as e:
                print(f"❌ Tool testing failed: {e}")

        except Exception as e:
            print(f"❌ Agentic Tool Calling import failed: {e}")

    except Exception as e:
        print(f"❌ Error during test execution: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()