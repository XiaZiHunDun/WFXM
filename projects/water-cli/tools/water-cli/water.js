#!/usr/bin/env node
'use strict';

/**
 * water.js — 终端喝水记录小工具（零第三方依赖，纯 Node 标准库）
 *
 * 数据默认保存在 ~/.water-cli/data.json，可用 WATER_DATA_DIR 覆盖目录。
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const DATA_DIR = process.env.WATER_DATA_DIR || path.join(os.homedir(), '.water-cli');
const DATA_FILE = path.join(DATA_DIR, 'data.json');
const DEFAULT_GOAL = 2000; // ml
const CUP_ML = 300;
const BOTTLE_ML = 500;

const color = (() => {
  const on = process.stdout.isTTY && !process.env.NO_COLOR;
  const wrap = (code) => (s) => (on ? `\u001b[${code}m${s}\u001b[0m` : String(s));
  return {
    dim: wrap('2'),
    bold: wrap('1'),
    green: wrap('32'),
    cyan: wrap('36'),
    yellow: wrap('33'),
  };
})();

// ---------- 存储 ----------

function emptyData() {
  return { goal: DEFAULT_GOAL, days: {} };
}

function load() {
  let raw;
  try {
    raw = fs.readFileSync(DATA_FILE, 'utf8');
  } catch (err) {
    if (err.code === 'ENOENT') return emptyData();
    throw err;
  }
  try {
    const parsed = JSON.parse(raw);
    return {
      goal: Number(parsed.goal) > 0 ? Number(parsed.goal) : DEFAULT_GOAL,
      days: parsed.days && typeof parsed.days === 'object' ? parsed.days : {},
    };
  } catch (err) {
    const backup = `${DATA_FILE}.bak`;
    fs.renameSync(DATA_FILE, backup);
    console.error(color.yellow(`数据文件损坏，已备份到 ${backup}，重新开始记录。`));
    return emptyData();
  }
}

function save(data) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  fs.writeFileSync(DATA_FILE, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
}

// ---------- 工具函数 ----------

function dayKey(date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function timeLabel(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--:--';
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function recordsOf(data, key) {
  const list = data.days[key];
  return Array.isArray(list) ? list : [];
}

function totalOf(records) {
  return records.reduce((sum, r) => sum + (Number(r.ml) || 0), 0);
}

function progressBar(ratio, width = 20) {
  const clamped = Math.max(0, Math.min(1, ratio));
  const filled = Math.round(clamped * width);
  return `${'█'.repeat(filled)}${'░'.repeat(width - filled)}`;
}

/** 解析 "250" / "250ml" / "2杯" / "1瓶" / "0.5L" */
function parseAmount(arg) {
  if (!arg) return null;
  const m = String(arg).trim().toLowerCase().match(/^(\d+(?:\.\d+)?)\s*(ml|毫升|杯|瓶|l|升)?$/);
  if (!m) return null;
  const value = Number(m[1]);
  const unit = m[2] || 'ml';
  const factor = { ml: 1, 毫升: 1, 杯: CUP_ML, 瓶: BOTTLE_ML, l: 1000, 升: 1000 }[unit] || 1;
  const ml = Math.round(value * factor);
  return ml > 0 && ml <= 20000 ? ml : null;
}

// ---------- 命令 ----------

function usage() {
  console.log(`用法: water <命令> [参数]

  add <量>      记录喝水，支持 250 / 250ml / 2杯 / 1瓶 / 0.5L
  today         查看今日进度（默认命令）
  week          最近 7 天统计
  undo          撤销今日最后一条记录
  goal [ml]     查看或修改每日目标
  help          显示本帮助

数据文件: ${DATA_FILE}`);
}

function cmdAdd(args) {
  const ml = parseAmount(args[0]);
  if (ml === null) {
    console.error('请给出有效水量，例如: water add 250 / water add 2杯');
    process.exitCode = 1;
    return;
  }
  const data = load();
  const key = dayKey();
  const records = recordsOf(data, key).slice();
  const amount = Number(args[1]) || ml;
  records.push({ ml, at: new Date().toISOString(), note: args.slice(1).join(' ') || undefined });
  data.days[key] = records;
  save(data);

  const total = totalOf(records);
  console.log(`${color.green('✔')} 已记录 ${ml}ml（${amount === ml ? '' : ''}今日累计 ${total}ml / ${data.goal}ml）`);
  if (total >= data.goal) {
    console.log(color.cyan('🎉 今日目标已达成！'));
  } else {
    console.log(color.dim(`还差 ${data.goal - total}ml`));
  }
}

function cmdToday() {
  const data = load();
  const key = dayKey();
  const records = recordsOf(data, key);
  const total = totalOf(records);
  const ratio = data.goal > 0 ? total / data.goal : 0;

  console.log(color.bold(`${key} 今日喝水`));
  console.log(
    `  ${color.cyan(progressBar(ratio))} ${Math.round(ratio * 100)}%`,
  );
  console.log(`  ${total}ml / ${data.goal}ml`);
  if (total < data.goal) {
    const left = data.goal - total;
    console.log(color.dim(`  还差 ${left}ml（约 ${Math.ceil(left / CUP_ML)} 杯）`));
  } else {
    console.log(color.green('  目标已达成 🎉'));
  }

  if (records.length) {
    console.log(color.dim('  ---'));
    for (const r of records) {
      const note = r.note ? `  ${color.dim(r.note)}` : '';
      console.log(`  ${timeLabel(r.at)}  ${r.ml}ml${note}`);
    }
  } else {
    console.log(color.dim('  今天还没有记录，试试: water add 250'));
  }
}

function cmdWeek() {
  const data = load();
  const days = [];
  for (let i = 6; i >= 0; i -= 1) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const key = dayKey(d);
    days.push({ key, total: totalOf(recordsOf(data, key)), isToday: i === 0 });
  }

  const goal = data.goal;
  console.log(color.bold(`最近 7 天（目标 ${goal}ml/天）`));
  for (const d of days) {
    const ratio = goal > 0 ? d.total / goal : 0;
    const tag = d.total >= goal ? color.green('✔') : ' ';
    const label = d.isToday ? color.cyan(d.key.slice(5)) : d.key.slice(5);
    console.log(
      `  ${label} ${progressBar(ratio, 14)} ${String(d.total).padStart(5)}ml ${tag}`,
    );
  }

  const logged = days.filter((d) => d.total > 0);
  const sum = logged.reduce((s, d) => s + d.total, 0);
  const avg = logged.length ? Math.round(sum / logged.length) : 0;
  const hit = days.filter((d) => d.total >= goal).length;
  console.log(
    color.dim(`  有记录 ${logged.length} 天，平均 ${avg}ml/天，达标 ${hit} 天`),
  );
}

function cmdUndo() {
  const data = load();
  const key = dayKey();
  const records = recordsOf(data, key).slice();
  if (!records.length) {
    console.log('今日没有可撤销的记录。');
    return;
  }
  const removed = records.pop();
  if (records.length) data.days[key] = records;
  else delete data.days[key];
  save(data);
  console.log(`已撤销 ${timeLabel(removed.at)} 的 ${removed.ml}ml，今日剩余 ${totalOf(records)}ml`);
}

function cmdGoal(args) {
  const data = load();
  if (!args.length) {
    console.log(`当前每日目标: ${data.goal}ml`);
    return;
  }
  const ml = parseAmount(args[0]);
  if (ml === null) {
    console.error('目标需要是有效水量，例如: water goal 2000');
    process.exitCode = 1;
    return;
  }
  data.goal = ml;
  save(data);
  console.log(`每日目标已设为 ${ml}ml`);
}

// ---------- 入口 ----------

function main(argv) {
  const [cmd, ...rest] = argv;
  switch (cmd) {
    case undefined:
    case 'today':
    case 'status':
      cmdToday();
      break;
    case 'add':
    case '+':
    case 'drink':
      cmdAdd(rest);
      break;
    case 'week':
    case 'stats':
      cmdWeek();
      break;
    case 'undo':
      cmdUndo();
      break;
    case 'goal':
      cmdGoal(rest);
      break;
    case 'help':
    case '-h':
    case '--help':
      usage();
      break;
    default: {
      // 直接 `water 250` 也当作记录
      const ml = parseAmount(cmd);
      if (ml !== null) {
        cmdAdd([cmd, ...rest]);
        break;
      }
      console.error(`未知命令: ${cmd}\n`);
      usage();
      process.exitCode = 1;
    }
  }
}

main(process.argv.slice(2));
