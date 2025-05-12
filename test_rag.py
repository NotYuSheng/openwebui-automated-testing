from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pyautogui
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
            driver.get(BASE_URL)
            chat_input = wait.until(EC.presence_of_element_located((By.ID, "chat-input")))
            
        except Exception as e:
            print(f"❌ Failed to load chat interface: {e}")
            driver.quit()
            return

        try:
            more_button = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[@aria-label='More']//*[name()='svg']")
                )
            )
            more_button.click()
            time.sleep(1)

            upload_button = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//div[contains(text(), 'Upload Files')]")
                )
            )
            upload_button.click()
            
            time.sleep(2)

            pyautogui.write(r"./sample-files/testrag.txt")  # Replace with your file path
            pyautogui.press("enter")
            
            time.sleep(30)

            driver.execute_script(
                "arguments[0].innerText = arguments[1];",
                chat_input,
                "What does the attached text file contain?",
            )
            chat_input.send_keys(Keys.RETURN)
            time.sleep(120)

            chatbot_response = wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//p[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'time')]",
                    )
                )
            )
            if "time" in chatbot_response.text.lower():
                print("✅ RAG test successful!")
            else:
                print("❌ RAG response validation failed!")

        except Exception as e:
            print(f"❌ RAG document test failed: {e}")
        finally:
            driver.quit()

    except Exception as e:
        print(f"❌ Error during test execution: {e}")
        driver.quit()


if __name__ == "__main__":
    main()
