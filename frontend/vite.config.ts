import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import fs from "node:fs";
import {createHash} from "node:crypto";
export default defineConfig({
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
