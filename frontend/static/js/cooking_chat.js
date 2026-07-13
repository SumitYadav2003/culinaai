document.addEventListener("DOMContentLoaded", function () {
  const chatRoot = document.querySelector("[data-cooking-chat-root]");

  if (!chatRoot) {
    return;
  }

  const askUrl = chatRoot.dataset.askUrl;
  const messagesBox = chatRoot.querySelector("[data-cooking-chat-messages]");
  const form = chatRoot.querySelector("[data-cooking-chat-form]");
  const input = chatRoot.querySelector("[data-cooking-chat-input]");
  const sendButton = chatRoot.querySelector("[data-cooking-chat-send]");
  const quickButtons = chatRoot.querySelectorAll("[data-cooking-chat-quick]");
  const loading = chatRoot.querySelector("[data-cooking-chat-loading]");
  const errorBox = chatRoot.querySelector("[data-cooking-chat-error]");

  function getCookie(name) {
    const value = "; " + document.cookie;
    const parts = value.split("; " + name + "=");

    if (parts.length === 2) {
      return parts.pop().split(";").shift();
    }

    return "";
  }

  function scrollToBottom() {
    if (messagesBox) {
      messagesBox.scrollTop = messagesBox.scrollHeight;
    }
  }

  function clearEmptyState() {
    const emptyState = chatRoot.querySelector("[data-cooking-chat-empty]");

    if (emptyState) {
      emptyState.remove();
    }
  }


  function cleanAssistantText(value) {
  let text = String(value || "");

  // Remove Markdown headings like ### Heading
  text = text.replace(/^\s*#{1,6}\s*/gm, "");

  // Remove Markdown bold/code markers
  text = text.replaceAll("**", "");
  text = text.replaceAll("__", "");
  text = text.replaceAll("`", "");

  // Convert markdown bullets into clean bullets
  text = text.replace(/^\s*[-*]\s+/gm, "• ");

  // Remove too many blank lines
  text = text.replace(/\n{3,}/g, "\n\n");

  return text.trim();
}

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function messageIcon(sender) {
    if (sender === "user") {
      return "bi-person-fill";
    }

    return "bi-robot";
  }

  function addMessage(sender, message, createdAt) {
    if (!messagesBox) {
      return;
    }

    clearEmptyState();

    const safeSender = sender === "user" ? "user" : "assistant";
    const wrapper = document.createElement("div");
    wrapper.className = "culina-chat-message " + safeSender;

    const displayMessage =
  safeSender === "assistant" ? cleanAssistantText(message) : message;

    wrapper.innerHTML = `
      <div class="culina-chat-message-avatar">
        <i class="bi ${messageIcon(safeSender)}"></i>
      </div>

      <div class="culina-chat-bubble">
        <p>${escapeHtml(displayMessage)}</p>
        <span class="culina-chat-meta">${escapeHtml(createdAt || "Just now")}</span>
      </div>
    `;

    messagesBox.appendChild(wrapper);
    scrollToBottom();
  }

  function setLoading(isLoading) {
    if (loading) {
      loading.classList.toggle("show", Boolean(isLoading));
    }

    if (sendButton) {
      sendButton.disabled = Boolean(isLoading);
    }

    quickButtons.forEach(function (button) {
      button.disabled = Boolean(isLoading);
    });
  }

  function showError(message) {
    if (!errorBox) {
      return;
    }

    if (message) {
      errorBox.textContent = message;
      errorBox.classList.add("show");
    } else {
      errorBox.textContent = "";
      errorBox.classList.remove("show");
    }
  }

  async function sendQuestion(question, quickPromptKey) {
    const cleanQuestion = String(question || "").trim();
    const cleanQuickPromptKey = String(quickPromptKey || "").trim();

    if (!cleanQuestion && !cleanQuickPromptKey) {
      showError("Please type a question or choose a quick prompt.");
      return;
    }

    showError("");
    setLoading(true);

    if (cleanQuestion) {
      addMessage("user", cleanQuestion, "Just now");
    }

    try {
      const response = await fetch(askUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({
          question: cleanQuestion,
          quick_prompt_key: cleanQuickPromptKey,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Assistant request failed.");
      }

      if (data.user_message && !cleanQuestion) {
        addMessage(
          "user",
          data.user_message.message,
          data.user_message.created_at
        );
      }

      if (data.assistant_message) {
        addMessage(
          "assistant",
          data.assistant_message.message,
          data.assistant_message.created_at
        );
      } else if (data.reply) {
        addMessage("assistant", data.reply, "Just now");
      }

      if (!data.success && data.error) {
  const hiddenValidationErrors = ["off_topic", "empty_question", "blocked"];

  if (!hiddenValidationErrors.includes(data.error)) {
    showError(data.error);
  } else {
    showError("");
  }
}
    } catch (error) {
      showError("Sorry, the cooking assistant could not respond right now.");
      addMessage(
        "assistant",
        "Sorry, I could not respond right now. Please try again.",
        "Just now"
      );
    } finally {
      setLoading(false);
    }
  }

  if (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();

      const question = input ? input.value : "";

      if (input) {
        input.value = "";
      }

      sendQuestion(question, "");
    });
  }

  quickButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      const promptKey = button.dataset.promptKey || "";
      const promptText = button.dataset.promptText || button.textContent.trim();

      sendQuestion(promptText, promptKey);
    });
  });

  const chatModal = document.getElementById("cookingAssistantModal");

  if (chatModal) {
    chatModal.addEventListener("shown.bs.modal", function () {
      scrollToBottom();

      if (input) {
        input.focus();
      }
    });
  }

  document
  .querySelectorAll(".culina-chat-message.assistant .culina-chat-bubble p")
  .forEach(function (messageElement) {
    messageElement.textContent = cleanAssistantText(messageElement.textContent);
  });

  scrollToBottom();
});
