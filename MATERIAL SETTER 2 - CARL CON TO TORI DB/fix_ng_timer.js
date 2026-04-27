// Fix for NG timer issue
const fs = require('fs');
const processes = ['process1.html', 'process3.html', 'process4.html', 'process5.html', 'process6.html', 'process7.html', 'process8.html', 'process9.html'];

processes.forEach(file => {
    let content = fs.readFileSync(file, 'utf8');
    
    // Find the end of handleNG function and add safeguard
    const regex = /(alert\(`NG detected![\s\S]*?\}\s*\})/g;
    const replacement = '$1\n\n// Extra safeguard: Ensure timer stays stopped after NG\nif (timerInterval) {\nclearInterval(timerInterval);\ntimerInterval = null;\nupdateStatus("STATUS: STOPPED", "stopped");\n}';
    
    content = content.replace(regex, replacement);
    
    fs.writeFileSync(file, content);
    console.log(`Fixed ${file}`);
});
