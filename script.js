(function () {
  var body = document.body;
  var toggle = document.querySelector("[data-lang-toggle]");
  var filters = Array.prototype.slice.call(document.querySelectorAll(".filter"));
  var papers = Array.prototype.slice.call(document.querySelectorAll(".paper-item"));
  var canvas = document.getElementById("signalCanvas");
  var context = canvas ? canvas.getContext("2d") : null;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function setLanguage(lang) {
    body.classList.toggle("lang-zh", lang === "zh");
    body.classList.toggle("lang-en", lang === "en");
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    try {
      localStorage.setItem("qzkinhit-home-lang", lang);
    } catch (error) {
      return;
    }
  }

  if (toggle) {
    var storedLanguage = "zh";
    try {
      storedLanguage = localStorage.getItem("qzkinhit-home-lang") || "zh";
    } catch (error) {
      storedLanguage = "zh";
    }
    setLanguage(storedLanguage);
    toggle.addEventListener("click", function () {
      setLanguage(body.classList.contains("lang-zh") ? "en" : "zh");
    });
  }

  filters.forEach(function (button) {
    button.addEventListener("click", function () {
      var topic = button.getAttribute("data-filter");
      filters.forEach(function (item) {
        item.classList.toggle("active", item === button);
      });
      papers.forEach(function (paper) {
        var topics = paper.getAttribute("data-topic") || "";
        paper.classList.toggle("is-hidden", topic !== "all" && topics.indexOf(topic) === -1);
      });
    });
  });

  if (!canvas || !context) {
    return;
  }

  var nodes = [];
  var width = 0;
  var height = 0;
  var pixelRatio = Math.min(window.devicePixelRatio || 1, 2);

  function resizeCanvas() {
    var rect = canvas.getBoundingClientRect();
    width = Math.max(1, Math.floor(rect.width));
    height = Math.max(1, Math.floor(rect.height));
    canvas.width = Math.floor(width * pixelRatio);
    canvas.height = Math.floor(height * pixelRatio);
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    buildNodes();
  }

  function buildNodes() {
    var count = width < 700 ? 42 : 72;
    nodes = [];
    for (var i = 0; i < count; i += 1) {
      nodes.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.34,
        vy: (Math.random() - 0.5) * 0.34,
        r: 1.5 + Math.random() * 2.4
      });
    }
  }

  function draw() {
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#111827";
    context.fillRect(0, 0, width, height);

    for (var i = 0; i < nodes.length; i += 1) {
      var node = nodes[i];
      if (!reduceMotion) {
        node.x += node.vx;
        node.y += node.vy;
      }
      if (node.x < -10) node.x = width + 10;
      if (node.x > width + 10) node.x = -10;
      if (node.y < -10) node.y = height + 10;
      if (node.y > height + 10) node.y = -10;

      for (var j = i + 1; j < nodes.length; j += 1) {
        var other = nodes[j];
        var dx = node.x - other.x;
        var dy = node.y - other.y;
        var dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 132) {
          var alpha = 1 - dist / 132;
          context.strokeStyle = "rgba(152, 241, 220, " + (alpha * 0.22).toFixed(3) + ")";
          context.lineWidth = 1;
          context.beginPath();
          context.moveTo(node.x, node.y);
          context.lineTo(other.x, other.y);
          context.stroke();
        }
      }

      context.fillStyle = i % 5 === 0 ? "rgba(232, 93, 79, 0.9)" : "rgba(152, 241, 220, 0.78)";
      context.beginPath();
      context.arc(node.x, node.y, node.r, 0, Math.PI * 2);
      context.fill();
    }

    if (!reduceMotion) {
      window.requestAnimationFrame(draw);
    }
  }

  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();
  draw();
})();
