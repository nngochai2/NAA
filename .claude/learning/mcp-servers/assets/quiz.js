/* Shared quiz widget for the MCP Servers teaching workspace.
   Self-contained, no network calls. Renders retrieval-practice questions with
   immediate feedback. Lesson authors: keep option text the same length/character
   count within a question so formatting never hints at the answer. */

(function (global) {
  function renderQuestion(container, q, index) {
    const lengths = q.options.map((o) => o.text.length);
    if (Math.max(...lengths) - Math.min(...lengths) > 2) {
      console.warn(
        `[quiz] Q${index + 1} options vary in length (${lengths.join(", ")}) — ` +
        "consider evening them out so length doesn't hint at the answer."
      );
    }

    const wrap = document.createElement("div");
    wrap.className = "quiz-q";

    const prompt = document.createElement("p");
    prompt.className = "quiz-prompt";
    prompt.textContent = `${index + 1}. ${q.prompt}`;
    wrap.appendChild(prompt);

    const list = document.createElement("div");
    list.className = "quiz-options";
    const name = `quiz-${index}-${Math.random().toString(36).slice(2, 8)}`;

    let answered = false;

    q.options.forEach((opt, i) => {
      const label = document.createElement("label");
      label.className = "quiz-option";

      const input = document.createElement("input");
      input.type = "radio";
      input.name = name;
      input.value = String(i);

      const span = document.createElement("span");
      span.textContent = opt.text;

      label.appendChild(input);
      label.appendChild(span);
      list.appendChild(label);

      input.addEventListener("change", () => {
        if (answered) return;
        answered = true;

        list.querySelectorAll(".quiz-option").forEach((el, j) => {
          el.classList.add(q.options[j].correct ? "quiz-correct" : "quiz-incorrect-dim");
        });
        label.classList.remove("quiz-incorrect-dim");
        if (!opt.correct) label.classList.add("quiz-incorrect");

        const feedback = document.createElement("p");
        feedback.className = "quiz-feedback " + (opt.correct ? "quiz-feedback-good" : "quiz-feedback-bad");
        feedback.textContent = opt.correct
          ? (q.explain ? `Correct. ${q.explain}` : "Correct.")
          : (q.explain ? `Not quite. ${q.explain}` : "Not quite — try to recall why before rereading.");
        wrap.appendChild(feedback);

        list.querySelectorAll("input").forEach((i2) => (i2.disabled = true));
      });
    });

    wrap.appendChild(list);
    container.appendChild(wrap);
  }

  function render(container, questions) {
    container.innerHTML = "";
    questions.forEach((q, i) => renderQuestion(container, q, i));
  }

  global.MCPQuiz = { render };
})(window);
