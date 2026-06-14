document.addEventListener("DOMContentLoaded", function () {
    const messages = document.querySelectorAll(".global-message");

    messages.forEach(function (message) {
        setTimeout(function () {
            message.classList.add("message-hide");

            setTimeout(function () {
                message.remove();
            }, 350);
        }, 2200);
    });
});