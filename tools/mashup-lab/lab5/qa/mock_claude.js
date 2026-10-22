
window.__sampleCalls = 0;
async function sample(input, opts){
  window.__sampleCalls++;
  const T = Object.fromEntries(opts.tools.map(t=>[t.name,t]));
  window.__toolNames = Object.keys(T);
  const r = await T.find_pairs.execute({vocal_genre:"mizr", beat_genre:"house", limit:3}, {signal:new AbortController().signal});
  await T.present_pairs.execute({pairs: r.pairs.slice(0,2).map(p=>({vocal_id:p.vocal_id, beat_id:p.beat_id, why:"אותו סולם ואותו קצב: מזרחית רכה מעל האוס מתגלגל"}))}, {});
  await T.update_view.execute({vocal_genre:"mizr", beat_genre:"afrohouse"}, {});
  const txt = "בחרתי לך **שני זוגות** חזקים. לוחצים על נגן מאש־אפ יחד כדי לשמוע.";
  opts.onText({text: txt, delta: txt});
  return {text: txt, truncated:false};
}
sample.limits = async()=>({maxPromptBytes:262144, tools:{maxCount:16}});
window.claude = { use: async (n)=> n==="sample" ? sample : null };
