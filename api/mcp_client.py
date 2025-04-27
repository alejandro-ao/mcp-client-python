from typing import Optional
from contextlib import AsyncExitStack
import traceback

# from utils.logger import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from datetime import datetime
from utils.logger import logger
import json
import os

from anthropic import Anthropic
from anthropic.types import Message


class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.llm = Anthropic()
        self.tools = []
        self.messages = []
        self.logger = logger

    # connect to the MCP server
    async def connect_to_server(self, server_script_path: str):
        try:
            is_python = server_script_path.endswith(".py")
            is_js = server_script_path.endswith(".js")
            if not (is_python or is_js):
                raise ValueError("Server script must be a .py or .js file")

            command = "python" if is_python else "node"
            server_params = StdioServerParameters(
                command=command, args=[server_script_path], env=None
            )

            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self.stdio, self.write = stdio_transport
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(self.stdio, self.write)
            )

            await self.session.initialize()

            self.logger.info("Connected to MCP server")

            mcp_tools = await self.get_mcp_tools()
            self.tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                for tool in mcp_tools
            ]

            self.logger.info(
                f"Available tools: {[tool['name'] for tool in self.tools]}"
            )

            return True

        except Exception as e:
            self.logger.error(f"Error connecting to MCP server: {e}")
            traceback.print_exc()
            raise

    # get mcp tool list
    async def get_mcp_tools(self):
        try:
            response = await self.session.list_tools()
            return response.tools
        except Exception as e:
            self.logger.error(f"Error getting MCP tools: {e}")
            raise

    # process query
    async def process_query(self, query: str):
        try:
            self.logger.info(f"Processing query: {query}")
            user_message = {"role": "user", "content": query}
            self.messages = [user_message]

            while True:
                response = await self.call_llm()

                # the response is a text message
                if response.content[0].type == "text" and len(response.content) == 1:
                    assistant_message = {
                        "role": "assistant",
                        "content": response.content[0].text,
                    }
                    self.messages.append(assistant_message)
                    await self.log_conversation()
                    break

                # the response is a tool call
                assistant_message = {
                    "role": "assistant",
                    "content": response.to_dict()["content"],
                }
                self.messages.append(assistant_message)
                await self.log_conversation()

                for content in response.content:
                    if content.type == "tool_use":
                        tool_name = content.name
                        tool_args = content.input
                        tool_use_id = content.id
                        self.logger.info(
                            f"Calling tool {tool_name} with args {tool_args}"
                        )
                        try:
                            result = await self.session.call_tool(tool_name, tool_args)
                            self.logger.info(f"Tool {tool_name} result: {result}...")
                            self.messages.append(
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "tool_result",
                                            "tool_use_id": tool_use_id,
                                            "content": result.content,
                                        }
                                    ],
                                }
                            )
                            await self.log_conversation()
                        except Exception as e:
                            self.logger.error(f"Error calling tool {tool_name}: {e}")
                            raise

            return self.messages

        except Exception as e:
            self.logger.error(f"Error processing query: {e}")
            raise

    # call llm
    async def call_llm(self):
        try:
            self.logger.info("Calling LLM")
            return self.llm.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                messages=self.messages,
                tools=self.tools,
            )
        except Exception as e:
            self.logger.error(f"Error calling LLM: {e}")
            raise

    # cleanup
    async def cleanup(self):
        try:
            await self.exit_stack.aclose()
            self.logger.info("Disconnected from MCP server")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            traceback.print_exc()
            raise

    async def log_conversation(self):
        os.makedirs("conversations", exist_ok=True)

        serializable_conversation = []

        for message in self.messages:
            try:
                serializable_message = {"role": message["role"], "content": []}

                # Handle both string and list content
                if isinstance(message["content"], str):
                    serializable_message["content"] = message["content"]
                elif isinstance(message["content"], list):
                    for content_item in message["content"]:
                        if hasattr(content_item, "to_dict"):
                            serializable_message["content"].append(
                                content_item.to_dict()
                            )
                        elif hasattr(content_item, "dict"):
                            serializable_message["content"].append(content_item.dict())
                        elif hasattr(content_item, "model_dump"):
                            serializable_message["content"].append(
                                content_item.model_dump()
                            )
                        else:
                            serializable_message["content"].append(content_item)

                serializable_conversation.append(serializable_message)
            except Exception as e:
                self.logger.error(f"Error processing message: {str(e)}")
                self.logger.debug(f"Message content: {message}")
                raise

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filepath = os.path.join("conversations", f"conversation_{timestamp}.json")

        try:
            with open(filepath, "w") as f:
                json.dump(serializable_conversation, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Error writing conversation to file: {str(e)}")
            self.logger.debug(f"Serializable conversation: {serializable_conversation}")
            raise
