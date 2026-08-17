const categories = [
  { name: 'Technology', slug: 'technology', description: 'Tools, models and infrastructure changing how we work and live.' },
  { name: 'Culture', slug: 'culture', description: 'How technology changes taste, behavior, media and everyday life.' },
  { name: 'Systems', slug: 'systems', description: 'The protocols, incentives and invisible structures underneath products.' },
  { name: 'Field Notes', slug: 'field-notes', description: 'Compact observations from products, cities and digital work.' },
];

const posts = [
  {
    title: 'The Quiet Machines Running the City', slug: 'the-quiet-machines-running-the-city', category: 'systems',
    excerpt: 'The most consequential technology in a city is often the technology nobody notices.',
    content: `<p>Most discussions about smart cities begin with screens: dashboards, maps, cameras and control rooms. The more interesting layer is quieter. It is the scheduling software that decides when a bus leaves a depot, the payment rail that clears a fare in milliseconds, the routing system that changes a delivery window, and the maintenance database that tells a technician which pump is likely to fail next.</p><p>These systems rarely look futuristic. Many are old, patched and deeply embedded. That is precisely why they matter. Infrastructure becomes powerful when it stops asking for attention and becomes a dependable background condition.</p><h2>Invisible does not mean simple</h2><p>A useful way to judge civic technology is not by how impressive the interface looks, but by how gracefully it handles exceptions. What happens when the network is slow? Can a human override a bad automated decision? Does the system degrade safely? Can another vendor read the data five years from now?</p><blockquote>Good infrastructure is often boring at the moment it works and extremely visible at the moment it fails.</blockquote><p>The next generation of urban software will probably feel less like a collection of apps and more like plumbing: standardized, interoperable and mostly unnoticed. That is not a failure of imagination. It is a sign that the machinery has finally earned its place.</p>`
  },
  {
    title: 'After the Feed: What Comes Next for the Open Web', slug: 'after-the-feed-what-comes-next-for-the-open-web', category: 'culture',
    excerpt: 'The infinite feed won because it removed decisions. The next web may win by giving some of those decisions back.',
    content: `<p>The feed solved a real problem: the internet became too large to navigate manually. Ranking systems compressed billions of possible pages into a single stream that always had something else to show. Convenience won, but it also flattened the web into a small number of recurring formats.</p><p>Now the cost is clearer. Publishers optimize for the ranking layer. Creators shape work around retention curves. Readers increasingly consume fragments without building a durable map of where those fragments came from.</p><h2>Navigation as a product again</h2><p>A different web does not require abandoning algorithms. It requires making discovery legible. Curated indexes, personal archives, RSS, topic pages, small communities and direct subscriptions all restore one important property: the user can understand why something is in front of them.</p><p>The opportunity is not nostalgia for 2005. It is combining modern search and machine intelligence with older web virtues: stable URLs, ownership, explicit relationships and the ability to leave one interface without losing the underlying information.</p><p>The feed will remain. But it may become one mode among many rather than the default shape of the internet.</p>`
  },
  {
    title: 'Small Models, Big Consequences', slug: 'small-models-big-consequences', category: 'technology',
    excerpt: 'AI does not need to be enormous to become ubiquitous. It needs to be cheap, fast and good enough at one job.',
    content: `<p>The public image of artificial intelligence is dominated by frontier models: enormous systems, expensive training runs and general-purpose interfaces. In practice, many of the applications that change daily work may come from the opposite direction.</p><p>A small model running close to the user can be cheaper, faster and easier to control. It can classify a document before it leaves a device, summarize a narrow stream of internal data, detect an anomaly in a machine or power an interface that would never justify a large inference bill.</p><h2>The economics change the product</h2><p>When inference becomes inexpensive, developers stop reserving AI for high-value moments. It can run continuously. That enables products built around ambient assistance rather than explicit prompts.</p><p>The trade-off is obvious: smaller systems know less and fail in narrower but still important ways. The design problem shifts from asking whether a model is intelligent to defining exactly where it is trusted.</p><blockquote>The useful unit of AI deployment may not be the smartest model. It may be the cheapest reliable decision.</blockquote><p>That distinction matters because ubiquity is usually driven by economics before spectacle.</p>`
  },
  {
    title: 'Why Interfaces Are Becoming Invisible', slug: 'why-interfaces-are-becoming-invisible', category: 'technology',
    excerpt: 'The best interface for a repeated task is increasingly the one that disappears after the intent is understood.',
    content: `<p>Software spent decades adding interface. More controls, more screens, more dashboards. The current direction is more interesting: mature products are beginning to remove steps.</p><p>Automation, natural-language input and predictive defaults make it possible to express an outcome instead of operating every intermediate control. The user asks for a result; the system composes the actions.</p><h2>Less interface, more responsibility</h2><p>This does not eliminate design. It raises the cost of bad design. A button makes its action visible before the user presses it. An automated agent may execute ten invisible actions before the user sees the consequence.</p><p>That means the new interface primitives are confirmation, reversibility, provenance and clear boundaries. Users need to know what happened, why it happened and how to undo it.</p><p>The future is not screenless. It is selective. Interfaces will remain dense where exploration matters and collapse where the intention is repetitive and well understood.</p>`
  },
  {
    title: 'The New Geography of Digital Work', slug: 'the-new-geography-of-digital-work', category: 'field-notes',
    excerpt: 'Remote work did not erase geography. It changed which parts of geography matter.',
    content: `<p>When work moved online, the first prediction was that location would stop mattering. The opposite happened in a subtler form. Geography became a bundle of constraints rather than a commute.</p><p>Time zones shape collaboration. Banking systems shape who can get paid. Visa rules determine how long a worker can stay. Internet reliability, housing costs and local social networks change the practical value of a nominally global job.</p><h2>A different map</h2><p>The relevant unit is no longer simply city versus office. It is a stack: residency, connectivity, payment rails, language, cost base and access to clients. Two places with similar rent can offer completely different operating environments.</p><p>That is why the geography of digital work is becoming more strategic, not less. Location is now something a worker can optimize, but optimization requires understanding the whole stack rather than chasing the cheapest apartment or the prettiest view.</p>`
  },
  {
    title: 'A Field Guide to Useful Friction', slug: 'a-field-guide-to-useful-friction', category: 'systems',
    excerpt: 'Not every extra step is bad UX. Some friction prevents errors, creates trust or improves judgment.',
    content: `<p>Product teams are trained to remove friction. Fewer clicks, shorter forms, instant checkout. This is usually correct, but it becomes a superstition when every pause is treated as a defect.</p><p>Some decisions deserve resistance. Sending money to a new account, deleting a project, publishing to a large audience or granting permanent access are actions where a small interruption can prevent a large mistake.</p><h2>Friction should buy something</h2><p>The test is simple: does the extra step create information, reflection or safety? A confirmation dialog that merely repeats the button label is noise. A confirmation that shows the exact consequences is useful.</p><p>Good friction is proportional. It appears at moments of asymmetry, where an action is easy to initiate and difficult to reverse. Everywhere else, remove it aggressively.</p><blockquote>The goal is not zero friction. The goal is zero meaningless friction.</blockquote>`
  },
  {
    title: 'The Return of Personal Software', slug: 'the-return-of-personal-software', category: 'culture',
    excerpt: 'Software is becoming cheap enough to build that one person can increasingly own tools shaped around one workflow.',
    content: `<p>For years, software economics pushed users toward general products. A tool needed enough customers to justify design, engineering, hosting and support. The result was software that served a category well enough rather than an individual perfectly.</p><p>Code generation, hosted infrastructure and reusable APIs are changing that threshold. A useful internal tool can now be created for a team of five. A personal dashboard can exist for one person. A tiny automation can be worth building even if nobody intends to sell it.</p><h2>From product choice to product composition</h2><p>This does not mean everyone becomes a software engineer. It means more people can specify behavior and combine existing components without waiting for a market to produce exactly the right application.</p><p>The important shift is ownership of workflow. Instead of adapting a process to the software, people can increasingly adapt the software to the process.</p><p>Mass-market applications will remain where network effects and reliability matter. Around them, a long tail of personal software is likely to grow.</p>`
  },
  {
    title: 'Designing for People Who Skip the Tutorial', slug: 'designing-for-people-who-skip-the-tutorial', category: 'field-notes',
    excerpt: 'Most users do not want to learn your product. They want enough evidence to make the next correct move.',
    content: `<p>Tutorials are often written from the product team's perspective: here are the concepts we built, the features we named and the sequence we think makes sense. Users arrive with a different question: what can I do here right now?</p><p>Good onboarding answers that question through the product itself. The first screen contains a meaningful object. The primary action looks primary. Empty states explain what will happen after a click. Examples are close enough to real work that users can modify them rather than starting from nothing.</p><h2>Teach at the moment of need</h2><p>Progressive disclosure works because learning is easier when information has immediate context. A three-minute tour before the user has formed a mental model is mostly memory tax.</p><p>The practical rule is to make the common path self-explanatory and move explanation next to the uncommon decisions. Documentation remains essential, but it should be a deeper layer rather than the entrance fee.</p><p>If a product only becomes obvious after a tutorial, the tutorial may be masking an interface problem.</p>`
  },
];

const pages = [
  {
    title: 'About', slug: 'about',
    content: `<p>OFFSET is an independent demo journal about technology, culture and the systems underneath everyday products.</p><p>This edition is intentionally designed as a complete editorial environment rather than a blank theme preview. The typography, archive, category pages and article templates all use the same visual system.</p><h2>Editorial principle</h2><p>Prefer useful signal over volume. Explain mechanisms instead of repeating announcements. Keep the interface quiet enough that the ideas can carry the page.</p>`
  },
  {
    title: 'Contact', slug: 'contact',
    content: `<p>This is demonstration content for the OFFSET WordPress build.</p><h2>Editorial</h2><p>For pitches, corrections or collaboration, replace this paragraph with the production contact channel before launch.</p><h2>Notes</h2><p>The current site is a fully editable WordPress installation. Posts, pages, categories, settings, themes and plugins can all be managed through the connected automation layer.</p>`
  },
];

function enc(v) { return encodeURIComponent(v); }

async function firstBySlug(api, type, slug) {
  const r = await api(`/wp-json/wp/v2/${type}?slug=${enc(slug)}&context=edit&per_page=1`);
  return Array.isArray(r.data) ? r.data[0] : null;
}

async function ensureCategory(api, item) {
  const found = await firstBySlug(api, 'categories', item.slug);
  if (found) {
    const r = await api(`/wp-json/wp/v2/categories/${found.id}`, { method: 'POST', body: item });
    return r.data;
  }
  return (await api('/wp-json/wp/v2/categories', { method: 'POST', body: item })).data;
}

async function ensureContent(api, type, item, extra = {}) {
  const found = await firstBySlug(api, type, item.slug);
  const body = { ...item, status: 'publish', ...extra };
  if (found) return (await api(`/wp-json/wp/v2/${type}/${found.id}`, { method: 'POST', body })).data;
  return (await api(`/wp-json/wp/v2/${type}`, { method: 'POST', body })).data;
}

export async function seedDemo(api) {
  const catMap = {};
  const categoryResults = [];
  for (const item of categories) {
    const c = await ensureCategory(api, item);
    catMap[item.slug] = c.id;
    categoryResults.push({ id: c.id, slug: c.slug, name: c.name });
  }

  const postResults = [];
  for (const item of posts) {
    const { category, ...body } = item;
    const p = await ensureContent(api, 'posts', body, { categories: [catMap[category]], comment_status: 'closed', ping_status: 'closed' });
    postResults.push({ id: p.id, slug: p.slug, title: p.title?.rendered || item.title, status: p.status, link: p.link });
  }

  const pageResults = [];
  for (const item of pages) {
    const p = await ensureContent(api, 'pages', item, { comment_status: 'closed', ping_status: 'closed' });
    pageResults.push({ id: p.id, slug: p.slug, title: p.title?.rendered || item.title, status: p.status, link: p.link });
  }

  const oldHello = await firstBySlug(api, 'posts', 'hello-world').catch(() => null);
  if (oldHello && !posts.some(p => p.slug === oldHello.slug)) {
    await api(`/wp-json/wp/v2/posts/${oldHello.id}?force=false`, { method: 'DELETE' }).catch(() => null);
  }

  const settings = (await api('/wp-json/wp/v2/settings', {
    method: 'POST',
    body: {
      title: 'OFFSET — Independent Journal',
      description: 'Technology, culture and the systems underneath.',
      posts_per_page: 7,
      show_on_front: 'posts',
      default_comment_status: 'closed',
      default_ping_status: 'closed'
    }
  })).data;

  return {
    seeded: true,
    categories: categoryResults,
    posts: postResults,
    pages: pageResults,
    settings: { title: settings.title, description: settings.description, posts_per_page: settings.posts_per_page, show_on_front: settings.show_on_front }
  };
}
