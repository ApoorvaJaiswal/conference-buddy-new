BASE = "/world-congress-north-america/agenda/sessions"

SESSIONS_HTML = """
<html><body>
<li><div>Session (30 min, incl. Q&amp;A)</div>
<div>Manufacturing trust: speed and safety in the age of agents</div>
<div>Mark Cavage &middot; President &amp; COO at Docker</div>
<p>Agents have made building software faster, but infrastructure has to catch up. In the world we now live in, developers review code they did not write, or do not review it at all. Trust has to move into the system itself and that is the argument here.</p>
<div>Topics</div><ul><li>Agents</li><li>Agentic AI</li><li>Docker</li></ul>
<a href="BASE/manufacturing-trust-speed-and-safety-in-the-age-of-agents-1318895">View Session Details</a></li>

<li><div>Workshop (120 min)</div><div>Pre-registration required</div>
<div>DeepAgents: Build Multi-Agent AI Systems That Actually Work</div>
<div>Apoorva Jaiswal &middot; Applied AI/ML Lead at JPMorgan Chase, Anjana Umapathy &middot; Applied AI/ML Lead &amp; VP at JPMorgan Chase</div>
<p>DeepAgents is a new LangChain framework built to solve exactly these problems, covering intelligent delegation, advanced planning, robust context preservation, and error recovery designed for production-grade workflows in a hands-on setting.</p>
<div>Topics</div><ul><li>Agents</li><li>LangChain</li><li>Python</li></ul>
<a href="BASE/deepagents-build-multi-agent-ai-systems-that-actually-work-1196173">View Session Details</a></li>

<li><div>Start-Up Presentation (5 min, no Q&amp;A)</div>
<div>each::labs: Close the Imagination Gap</div>
<div>Eftal Yurtseven &middot; Co-Founder &amp; CEO at each::labs</div>
<p>The gap between what people imagine and what AI creates is a production problem and this is how we close it with one API, six hundred models, routing and failover built in for production economics.</p>
<a href="BASE/each-labs-close-the-imagination-gap-1310739">View Session Details</a></li>
</body></html>
""".replace("BASE", BASE)

SCHEDULE_HTML = """
<html><body>
<h2>Day 1</h2>
<a href="BASE/manufacturing-trust-speed-and-safety-in-the-age-of-agents-1318895">
9:45 AM&ndash;10:15 AM Mainstage <b>Manufacturing trust: speed and safety in the age of agents</b> Applied AI Mark Cavage</a>
<a href="BASE/taming-rogue-agents-observability-driven-evaluation-for-production-reliability-1196166">
11:40 AM&ndash;12:10 PM Stage 4 <b>Taming Rogue Agents</b> Security &amp; Privacy Anjana Umapathy</a>
<a href="BASE/each-labs-close-the-imagination-gap-1310739">
12:40 PM&ndash;12:45 PM Outdoor Stage <b>each::labs: Close the Imagination Gap</b> Startups &amp; Innovation Eftal Yurtseven</a>
<h2>Day 0</h2>
<a href="BASE/deepagents-build-multi-agent-ai-systems-that-actually-work-1196173">
1:15 PM&ndash;3:15 PM Stage 9 Workshop <b>DeepAgents: Build Multi-Agent AI Systems That Actually Work</b> AI Agents Apoorva Jaiswal</a>
</body></html>
""".replace("BASE", BASE).replace("&ndash;", "\u2013")

# Regression: the workshops grid stacks programmes, so a Day 0 workshop can sit
# physically below a Day 2 heading. Position-based day inference put the
# DeepAgents workshop (really Wed 23 Sep) on Friday. It must come back either
# correct or unknown - never confidently wrong.
WORKSHOPS_HTML = """
<html><body>
<h2>Day 2 &middot; Fri, Sep 25</h2>
<a href="BASE/some-friday-workshop-1306074">
1:15 PM&ndash;3:15 PM Stage 8 Workshop <b>From Signal to Action</b> DevOps &amp; Platform Engineering</a>

<h2>Workshops &amp; Masterclasses</h2>
<div class="row"><time datetime="2026-09-23T13:15:00-07:00">Wed 1:15 PM</time>
<a href="BASE/deepagents-build-multi-agent-ai-systems-that-actually-work-1196173">
1:15 PM&ndash;3:15 PM Stage 9 Workshop <b>DeepAgents: Build Multi-Agent AI Systems That Actually Work</b> AI Agents Pre-registration required</a></div>
</body></html>
""".replace("BASE", BASE).replace("&ndash;", "\u2013")
