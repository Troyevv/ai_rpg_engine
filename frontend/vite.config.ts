import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import fs from "node:fs";
import {execFileSync} from "node:child_process";
import {createHash} from "node:crypto";
let revision: string | null = null;
try {
  revision = execFileSync('git', ['rev-parse', '--short=12', 'HEAD'], {cwd:__dirname, encoding:'utf8', stdio:['ignore','pipe','ignore']}).trim();
} catch { /* ZIP installations are identified by their compiled asset. */ }
export default defineConfig({
  define: {'import.meta.env.VITE_CLIENT_REVISION': JSON.stringify(revision)},
  plugins: [react(), tailwindcss(), {name:'version-service-worker',closeBundle(){
 const root=path.resolve(__dirname,'dist');if(!fs.existsSync(root+'/sw.js'))return;
 const digest=createHash('sha256').update(fs.readFileSync(root+'/index.html'));
 for(const file of fs.readdirSync(path.resolve(__dirname,'public'),{recursive:true}).sort()){const source=path.resolve(__dirname,'public',String(file));if(fs.statSync(source).isFile())digest.update(fs.readFileSync(source))}
 const hash=digest.digest('hex').slice(0,16);
 const sw=fs.readFileSync(root+'/sw.js','utf8').replace('__BUILD_ID__',hash);fs.writeFileSync(root+'/sw.js',sw);
 }}],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
