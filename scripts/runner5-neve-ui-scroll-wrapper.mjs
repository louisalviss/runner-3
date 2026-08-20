import fs from 'fs';
import { pathToFileURL } from 'url';
const srcPath='scripts/runner5-neve-official-ui-import.mjs';
let s=fs.readFileSync(srcPath,'utf8');
const needle="if(!await card.isVisible({timeout:3000}).catch(()=>false))throw new Error('official_photography_studio_card_missing:'+text.slice(0,900));";
const replacement=`if(!await card.isVisible({timeout:3000}).catch(()=>false)){
    await clickAny(wp,[/^Portfolio$/i,/Photography/i],{timeout:600}).catch(()=>false);
    await wp.waitForTimeout(1200);
    for(let load=0;load<45;load++){
      card=wp.getByText(/^Photography Studio$/i).first();
      if(await card.isVisible({timeout:250}).catch(()=>false))break;
      await wp.mouse.wheel(0,1400);await wp.waitForTimeout(450);
    }
  }
  if(!await card.isVisible({timeout:1000}).catch(()=>false))throw new Error('official_photography_studio_card_missing_after_scroll:'+(await bodyText(wp)).slice(-1500));`;
if(!s.includes(needle))throw new Error('patch_target_missing');
s=s.replace(needle,replacement);
const tmp='scripts/runner5-neve-ui-patched.runtime.mjs';fs.writeFileSync(tmp,s);await import(pathToFileURL(process.cwd()+'/'+tmp).href);
