afrom selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
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
                    (By.XPATH, "//button[@type='submit' and contains(text(),'Sign in')]")
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
            driver.get("http://localhost:8080/admin/functions")
            time.sleep(2)

            # Click the "Add Function" button
            add_func_btn = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(@href,'/admin/functions/create')]")
                )
            )
            add_func_btn.click()

            # Fill function name
            func_name = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//input[@placeholder='Function Name']")
                )
            )
            func_name.send_keys("Native Tool Calling Pipe")

            # Fill function description
            func_desc = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//input[@placeholder='Function Description']")
                )
            )
            func_desc.send_keys(
                "Seamless OpenAI API-native tool calling with streaming and multi-call support"
            )

            time.sleep(1)

            function_code = r'''"""
title: Native Tool Calling Pipe
author: Marcel Samyn
author_url: https://samyn.co
git_url: https://github.com/iamarcel/open-webui-utils.git
description: Seamless OpenAI API-native tool calling with streaming and multi-call support
required_open_webui_version: 0.5.0
version: 0.2.3
license: MIT
"""

from abc import ABC, abstractmethod
import inspect
import json
from typing import (
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Any,
    Iterable,
    Literal,
    Mapping,
    NotRequired,
    Optional,
    TypedDict,
    Union,
)
import html
import asyncio
import uuid
import httpx
from openai.resources.chat import Chat
from pydantic import BaseModel, Field
from openai import NotGiven, OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)
from openai.types.shared_params.function_definition import FunctionDefinition
from open_webui.models.chats import ChatForm, Chats


# Patched HTTPClient because the OpenAI API passes "proxies" which doesn't exist in
# httpx >= 0.28
class CustomHTTPClient(httpx.Client):
    def __init__(self, *args, **kwargs):
        kwargs.pop("proxies", None)  # Remove the 'proxies' argument if present
        super().__init__(*args, **kwargs)


class ToolSpecParametersProperty(TypedDict):
    description: str
    type: str
    items: NotRequired[dict[str, str]]
    default: NotRequired[Any]
    enum: NotRequired[list[str]]
    maxItems: NotRequired[int]
    minItems: NotRequired[int]
    prefixItems: NotRequired[list[dict[str, Any]]]


class ToolSpecParameters(TypedDict):
    properties: dict[str, ToolSpecParametersProperty]
    required: NotRequired[list[str]]
    type: str
    additionalProperties: NotRequired[bool]


class ToolSpec(TypedDict):
    name: str
    description: str
    parameters: ToolSpecParameters


class ToolCallable(TypedDict):
    toolkit_id: str
    callable: Callable
    spec: ToolSpec
    pydantic_model: NotRequired[BaseModel]
    file_handler: bool
    citation: bool


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str


class EventEmitterMessageData(TypedDict):
    content: str


class EventEmitterStatusData(TypedDict):
    description: str
    done: Optional[bool]


class EventEmitterStatus(TypedDict):
    type: Literal["status"]
    data: EventEmitterStatusData


class EventEmitterMessage(TypedDict):
    type: Literal["message"]
    data: EventEmitterMessageData


class Metadata(TypedDict):
    chat_id: str
    user_id: str
    message_id: str


class EventEmitter:
    def __init__(
        self,
        __event_emitter__: Optional[
            Callable[[Mapping[str, Any]], Awaitable[None]]
        ] = None,
    ):
        self.event_emitter = __event_emitter__

    async def emit(
        self, message: Union[EventEmitterMessage, EventEmitterStatus]
    ) -> None:
        if self.event_emitter:
            maybe_future = self.event_emitter(message)
            if asyncio.isfuture(maybe_future) or inspect.isawaitable(maybe_future):
                await maybe_future

    async def status(self, description: str, done: Optional[bool] = None) -> None:
        await self.emit(
            EventEmitterStatus(
                type="status",
                data=EventEmitterStatusData(description=description, done=done),
            )
        )

    async def result(self, summary: str, content: str) -> None:
        await self.emit(
            EventEmitterMessage(
                type="message",
                data=EventEmitterMessageData(
                    content=f'\n<details type="tool_calls" done="true" results="{html.escape(content)}">\n<summary>{summary}</summary>\n{content}\n</details>',
                ),
            )
        )


class ToolCallResult(BaseModel):
    tool_call: ToolCall
    result: Optional[str] = None
    error: Optional[str] = None

    def to_display(self) -> str:
        if self.error:
            return f'\n\n<details type="tool_calls" done="true">\n<summary>Error executing {self.tool_call.name}</summary>\n{self.error}\n</details>\n\n'
        return (
            f'\n\n<details type="tool_calls" done="true" results="{html.escape(self.result) if self.result else ""}">'
            f"\n<summary>Executed {self.tool_call.name}</summary>\n"
            f"Tool ran with arguments: {self.tool_call.arguments}\n\n"
            f'Result:\n{json.loads(self.result) if self.result else "None"}\n</details>\n\n'
        )


class ToolCallingChunk(BaseModel):
    message: Optional[str] = None
    tool_calls: Optional[Iterable[ToolCall]] = None


class ToolCallingModel(ABC):
    """
    ToolCallingModel is an abstract class that defines the interface for a tool calling model.
    """

    @abstractmethod
    def stream(
        self,
        body: dict,
        __tools__: dict[str, ToolCallable] | None,
    ) -> AsyncIterator[ToolCallingChunk]:
        """
        Takes the request body and optional tools, returning ToolCallingChunks.
        When the chunk contains a message, it's immediately shown to the user.
        Tool calls are collected until the stream ends, and then executed.
        When tools have been executed, this method is called again with the tool results,
        allowing the model to react to it or call new tools.
        """
        raise NotImplementedError

    @abstractmethod
    def append_tool_calls(self, body: dict, tool_calls: Iterable[ToolCall]) -> None:
        """
        Append tool calls to the request body.
        """
        raise NotImplementedError

    @abstractmethod
    def append_results(self, body: dict, results: Iterable[ToolCallResult]) -> None:
        """
        Append the results of tool calls to the request body.
        """
        raise NotImplementedError


class OpenAIToolCallingModel(ToolCallingModel):
    def __init__(self, client: OpenAI, model_id: str, use_prompt_caching: bool):
        self.client = client
        self.model_id = model_id
        self.use_prompt_caching = use_prompt_caching

    async def stream(
        self,
        body: dict,
        __tools__: dict[str, ToolCallable] | None,
    ) -> AsyncIterator[ToolCallingChunk]:
        tools = self._map_tools(__tools__)
        messages: list[ChatCompletionMessageParam] = body["messages"]

        tool_calls_map: dict[str, ToolCall] = {}
        last_tool_call_id: Optional[str] = None

        if self.use_prompt_caching:
            # Find last user message
            last_user_message: Optional[ChatCompletionMessageParam] = None
            for message in messages:
                if "role" in message and message["role"] == "user":
                    last_user_message = message
                    break

            # Set caching property
            if last_user_message and "content" in last_user_message:
                contents = last_user_message["content"]
                if isinstance(contents, list):
                    contents[-1]["cache_control"] = {"type": "ephemeral"}  # type: ignore
                elif isinstance(contents, str):
                    last_user_message["content"] = [  # type: ignore
                        {
                            "type": "text",
                            "text": contents,
                            "cache_control": {"type": "ephemeral"},
                        },
                    ]

        for chunk in self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            stream=True,
            tools=tools or NotGiven(),
        ):
            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            if delta.content:
                yield ToolCallingChunk(message=delta.content)

            for tool_call in delta.tool_calls or []:
                # Tool call id is only given when the block starts.
                # Keep track of it as function name and arguments come in in later chunks.
                tool_call_id = tool_call.id or last_tool_call_id
                last_tool_call_id = tool_call_id

                if not tool_call_id:
                    continue

                if tool_call_id not in tool_calls_map:
                    tool_calls_map[tool_call_id] = ToolCall(
                        id=tool_call_id, name="", arguments=""
                    )

                if tool_call.function:
                    if tool_call.function.name:
                        tool_calls_map[tool_call_id].name = tool_call.function.name
                    if tool_call.function.arguments:
                        tool_calls_map[
                            tool_call_id
                        ].arguments += tool_call.function.arguments

            if finish_reason:
                if tool_calls_map:
                    yield ToolCallingChunk(tool_calls=tool_calls_map.values())
                return

    def append_results(self, body: dict, results: Iterable[ToolCallResult]):
        if "messages" in body:
            for result in results:
                body["messages"].append(self._map_result(result))

    def append_tool_calls(self, body: dict, tool_calls: Iterable[ToolCall]):
        if "messages" in body:
            tool_call_message = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                        },
                    }
                    for tool_call in tool_calls
                ],
            }

            if body["messages"][-1]["role"] == "assistant":
                body["messages"][-1]["tool_calls"] = tool_call_message["tool_calls"]
            else:
                body["messages"].append(tool_call_message)

    def append_assistant_message(self, body: dict, message: str) -> None:
        if "messages" in body:
            body["messages"].append(
                {
                    "role": "assistant",
                    "content": message,
                }
            )

    def _map_result(self, result: ToolCallResult) -> dict[str, str]:
        if result.error:
            return {
                "role": "tool",
                "tool_call_id": result.tool_call.id,
                "content": result.error,
            }
        return {
            "role": "tool",
            "tool_call_id": result.tool_call.id,
            "content": result.result or "",
        }

    def _map_tools(
        self, tool_specs: dict[str, ToolCallable] | None
    ) -> list[ChatCompletionToolParam]:
        openai_tools: list[ChatCompletionToolParam] = []
        for tool in tool_specs.values() if tool_specs else []:
            function_definition: FunctionDefinition = {
                "name": tool["spec"]["name"],
                "description": tool["spec"].get("description"),
                "parameters": tool["spec"].get("parameters"),  # type: ignore
            }
            openai_tools.append(
                {
                    "type": "function",
                    "function": function_definition,
                }
            )
        return openai_tools


class Pipe:
    class Valves(BaseModel):
        OPENAI_API_KEY: str = Field(default="", description="OpenAI API key")
        OPENAI_BASE_URL: str = Field(
            default="https://api.openai.com/v1", description="OpenAI API base URL"
        )
        MODEL_IDS: list[str] = Field(
            default=["gpt-4o-mini"],
            description="List of model IDs to enable (comma-separated)",
        )
        ENABLE_PROMPT_CACHING: bool = Field(
            default=True,
            description="Enable prompt caching (only affects Anthropic models)",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.type = "manifold"
        self.name = "native-tool/"

    def pipes(self) -> list[dict]:
        return [
            {"id": model_id, "name": model_id} for model_id in self.valves.MODEL_IDS
        ]

    async def execute_tool(
        self,
        tool_call: ToolCall,
        tools: dict[str, ToolCallable],
        ev: EventEmitter,
    ) -> ToolCallResult:
        try:
            tool = tools.get(tool_call.name)
            if not tool:
                raise ValueError(f"Tool '{tool_call.name}' not found")

            if tool_call.arguments:
                parsed_args = json.loads(tool_call.arguments)
                await ev.status(
                    f"Executing tool '{tool_call.name}' with arguments: {parsed_args}"
                )
            else:
                parsed_args = {}

            result = await tool["callable"](**parsed_args)

            return ToolCallResult(
                tool_call=tool_call,
                result=json.dumps(result),
            )
        except json.JSONDecodeError:
            return ToolCallResult(
                tool_call=tool_call,
                error=f"Failed to parse arguments for tool '{tool_call.name}'",
            )
        except Exception as e:
            return ToolCallResult(
                tool_call=tool_call,
                error=f"Error executing tool '{tool_call.name}': {str(e)}",
            )

    async def pipe(
        self,
        body: dict,
        __metadata__: Metadata,
        __user__: dict | None = None,
        __task__: str | None = None,
        __tools__: dict[str, ToolCallable] | None = None,
        __event_emitter__: Callable[[Mapping[str, Any]], Awaitable[None]] | None = None,
    ) -> AsyncGenerator[str, None]:
        if __task__ == "function_calling":
            # Go away open-webui let me deal with it myself
            return

        client = OpenAI(
            api_key=self.valves.OPENAI_API_KEY,
            base_url=self.valves.OPENAI_BASE_URL,
            http_client=CustomHTTPClient(),
        )

        model_id = body["model"] or ""
        model_id = model_id[model_id.find(".") + 1 :]

        model = OpenAIToolCallingModel(
            client, model_id, self.valves.ENABLE_PROMPT_CACHING
        )
        ev = EventEmitter(__event_emitter__)

        while True:
            await ev.status("Generating response...")
            tool_calls: list[ToolCall] = []

            # Stream model response: pass text content through and collect tool calls
            message = ""
            async for chunk in model.stream(body, __tools__):
                tool_calls = list(chunk.tool_calls) if chunk.tool_calls else tool_calls

                if chunk.message:
                    message += chunk.message
                    yield chunk.message

            model.append_assistant_message(body, message)

            if not tool_calls:
                # No tools to execute, stop the loop
                await ev.status("Done", done=True)
                break

            if not __tools__:
                raise ValueError("No tools provided while tool call was requested")

            model.append_tool_calls(body, tool_calls)

            # Execute tools and process results
            await ev.status("Executing tools...")
            tool_call_results = [
                await self.execute_tool(
                    tool_call,
                    __tools__,
                    ev,
                )
                for tool_call in tool_calls
            ]

            # Add to body for next iteration(s)
            model.append_results(body, tool_call_results)

            # Yield result for later conversation turns
            for result in tool_call_results:
                yield result.to_display()

            tool_calls = []
            await ev.status("Tool execution complete", done=True)

        return'''

            pyperclip.copy(function_code)

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
            except Exception as e:
                print(f"ℹ️ No update popup found: {e}")

            # Click Save
            save_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Save')]"))
            )
            save_button.click()

            # Try to find and click confirm button, if not found continue to test
            try:
                confirm_button = wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(text(),'Confirm')]")
                    )
                )
                confirm_button.click()
                time.sleep(15)

                # Toggle disabled button
                try:
                    toggle_disabled_button = wait.until(EC.element_to_be_clickable((
                        By.XPATH, "//div[@aria-label='Disabled']//button[@role='switch']"
                    )))
                    toggle_disabled_button.click()
                    time.sleep(1)
                except Exception as e:
                    print(f"ℹ️ Toggle disabled button not found: {e}")

                # Valves configuration
                try:
                    valves_button = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(@class, 'self-center') and contains(@class, 'text-sm') and contains(@class, 'px-2')]")
                    ))
                    valves_button.click()
                    print("✅ Clicked Valves button")
                    time.sleep(1)

                    default_button = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(@class, 'p-1') and contains(@class, 'px-3') and contains(@class, 'text-xs')]")
                    ))
                    default_button.click()
                    print("✅ Clicked Default button")
                    time.sleep(5)

                    api_key_input = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//input[contains(@class, 'w-full') and contains(@class, 'px-4')]")
                    ))
                    api_key_input.click()
                    api_key_input.clear()
                    api_key_input.send_keys("") # Add OpenApi Key inside the quotes
                    time.sleep(5)

                    model_id_input = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//input[contains(@class, 'w-full') and contains(@class, 'rounded-lg') and contains(@placeholder, 'Model Ids')]")
                    ))
                    model_id_input.click()
                    model_id_input.clear()
                    model_id_input.send_keys("gpt-3.5-turbo")
                    print("✅ Entered Model ID: gpt-3.5-turbo")

                    save_button = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(@class, 'px-3.5') and contains(@class, 'py-1.5') and contains(@class, 'text-sm') and contains(text(), 'Save')]")
                    ))
                    save_button.click()
                    print("✅ Clicked Save button")
                    time.sleep(2)
                except Exception as e:
                    print(f"❌ Error in valves configuration: {e}")

            except Exception as e:
                print(f"ℹ️ Confirm button not found or other error, proceeding to test tool: {e}")

            # Test the tool functionality
            try:
                driver.get(BASE_URL)
                time.sleep(2)
 
                more_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='More']//*[name()='svg']")))
                more_btn.click()

                toggle_tool = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'cursor-pointer') and @role='switch']")))
                toggle_tool.click()

                chat_input = wait.until(EC.presence_of_element_located((By.ID, "chat-input")))
                chat_input.click()
                chat_input.send_keys("What is the current time in Singapore")
                chat_input.send_keys(Keys.RETURN)
                time.sleep(10)

                try:
                    response = wait.until(
                        EC.presence_of_element_located(
                            (By.XPATH, "//div[contains(text(), 'Current Time')]")
                        )
                    )
                    print(f"✅ Tool response received: {response.text}")
                except Exception as e:
                    print(f"❌ No tool response detected: {e}")

            except Exception as e:
                print(f"❌ Tool testing failed: {e}")

        except Exception as e:
            print(f"❌ Native Tool Calling import failed: {e}")

    except Exception as e:
        print(f"❌ Error during test execution: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
