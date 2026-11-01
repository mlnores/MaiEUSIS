const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
// Execute the exact ordered script tags, including registered task adapters.
exports.loadScripts=(html,context,root=path.resolve(__dirname,'..'))=>{
 for(const m of html.matchAll(/<script(?:\s+src="([^"]+)")?[^>]*>([\s\S]*?)<\/script>/g)){
  const code=m[1]?fs.readFileSync(path.join(root,'socratic_prototype/static',m[1].replace(/^\//,'')),'utf8'):m[2];
  vm.runInContext(code,context,{filename:m[1]||'task-shell.js'});
 }
};
