async function updateDashboard() {
  const res = await fetch('/status');
  const data = await res.json();

  // Core data
  document.getElementById("bias").innerText = data.bias;
  document.getElementById("sweep").innerText = data.sweep;
  document.getElementById("displacement").innerText = data.displacement;
  document.getElementById("structure").innerText = data.structure;
  document.getElementById("retest").innerText = data.retest;

  document.getElementById("loss").innerText = "$" + data.loss;
  document.getElementById("trades").innerText = data.trades;
  document.getElementById("session").innerText = data.session;

  // Score system
  let score = 0;

  if (data.sweep === "Confirmed") score += 2;
  if (data.displacement === "Strong") score += 2;
  if (data.structure !== "None") score += 2;
  if (data.retest === "Valid") score += 3;

  // Decision
  const decision = document.getElementById("decision");

  if (score >= 7) {
    decision.innerText = "VALID TRADE";
    decision.className = "decision valid";
  } else {
    decision.innerText = "NO TRADE";
    decision.className = "decision invalid";
  }

  document.getElementById("confidence").innerText = (score * 10) + "%";

  // State Machine Highlight
  document.querySelectorAll(".step").forEach(el => el.classList.remove("active-step"));

  if (data.retest === "Valid") {
    document.getElementById("step-retest").classList.add("active-step");
  } else if (data.structure !== "None") {
    document.getElementById("step-structure").classList.add("active-step");
  } else if (data.displacement === "Strong") {
    document.getElementById("step-disp").classList.add("active-step");
  } else if (data.sweep === "Confirmed") {
    document.getElementById("step-sweep").classList.add("active-step");
  } else {
    document.getElementById("step-bias").classList.add("active-step");
  }

}

setInterval(updateDashboard, 2000);
