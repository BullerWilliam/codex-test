const readline = require("readline");

const API_URL = "https://text.pollinations.ai/openai";
const MODEL = "gpt-oss-20b";

const history = [
  {
    role: "system",
    content:
      "You are a helpful AI assistant in a terminal chat. Keep answers clear and concise unless asked for more detail.",
  },
];

async function askModel(message) {
  history.push({ role: "user", content: message });

  const response = await fetch(API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: MODEL,
      messages: history,
    }),
  });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  const data = await response.json();
  const reply = data?.choices?.[0]?.message?.content;

  if (!reply) {
    throw new Error("API returned no assistant reply.");
  }

  history.push({ role: "assistant", content: reply });
  return reply;
}

function resetChat() {
  history.splice(1);
}

async function main() {
  console.log("Cloud AI console chat");
  console.log(`Provider: ${API_URL}`);
  console.log(`Model: ${MODEL}`);
  console.log("Commands: /reset, /exit");
  console.log("");

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    prompt: "you> ",
  });

  rl.prompt();

  rl.on("line", async (line) => {
    const input = line.trim();

    if (!input) {
      rl.prompt();
      return;
    }

    if (input === "/exit") {
      rl.close();
      return;
    }

    if (input === "/reset") {
      resetChat();
      console.log("ai> Conversation reset.");
      rl.prompt();
      return;
    }

    try {
      const reply = await askModel(input);
      console.log(`ai> ${reply}`);
    } catch (error) {
      console.log(`ai> Error: ${error.message}`);
    }

    rl.prompt();
  });

  rl.on("close", () => {
    process.exit(0);
  });
}

main().catch((error) => {
  console.error(`Fatal: ${error.message}`);
  process.exit(1);
});
