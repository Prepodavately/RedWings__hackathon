import React, { useState } from 'react';
import {
  ASCII_REPO_TREE,
  REPO_FILES,
  TEAM_WORKFLOW_ROLES,
  RepoFileSpec,
} from '../utils/repoArchitecture';
import {
  FULL_TEAM_TZ_MARKDOWN,
  downloadFile,
  downloadTeamTzWordDoc,
} from '../utils/tzDocument';
import { Copy, Check, FolderTree, Download } from 'lucide-react';

export const GitHubArchitectureSection: React.FC = () => {
  const [selectedFilePath, setSelectedFilePath] = useState<string>(REPO_FILES[0].path);
  const [roleFilter, setRoleFilter] = useState<
    'all' | 'dev1_data' | 'dev2_scoring' | 'dev3_model' | 'dev4_ui'
  >('all');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const visibleFiles =
    roleFilter === 'all'
      ? REPO_FILES
      : REPO_FILES.filter((f) => f.ownerRole === roleFilter || f.ownerRole === 'all');

  const activeFile: RepoFileSpec =
    visibleFiles.find((f) => f.path === selectedFilePath) || visibleFiles[0] || REPO_FILES[0];

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard?.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1800);
  };

  const handleDownloadBootstrapScript = () => {
    const scriptLines = [
      '#!/usr/bin/env bash',
      '# Автогенератор каркаса репозитория Red Wings Network Strategy (Команда ПМИ)',
      'set -e',
      'mkdir -p config data/raw data/processed data/mocks src/schemas src/parsers src/scoring src/models src/mocks src/ui notebooks tests',
      'touch data/raw/rosstat_cities.csv data/raw/rosaviatsia_2025.csv data/raw/schedules_raw.json',
      'touch data/processed/.gitkeep data/mocks/mock_top_cities.json data/mocks/mock_hypotheses.json',
      'touch config/settings.yaml config/weights_default.json',
      'touch src/__init__.py src/schemas/__init__.py src/schemas/contracts.py',
      'touch src/parsers/__init__.py src/parsers/rosstat_loader.py src/parsers/schedule_scraper.py src/parsers/build_dataset.py',
      'touch src/scoring/__init__.py src/scoring/normalizer.py src/scoring/city_scorer.py',
      'touch src/models/__init__.py src/models/sj100_fleet.py src/models/unit_economics.py',
      'touch src/mocks/__init__.py src/mocks/mock_provider.py',
      'touch src/ui/__init__.py src/ui/sidebar_controls.py src/ui/kpi_cards.py src/ui/map_renderer.py src/ui/roadmap_chart.py',
      'touch notebooks/01_eda_rosaviatsia.ipynb notebooks/02_scoring_check.ipynb',
      'touch tests/test_contracts.py tests/test_unit_economics.py app.py requirements.txt Makefile README.md',
      'echo "Каркас репозитория Red Wings успешно создан!"',
    ].join('\n');

    downloadFile(scriptLines, 'init_redwings_repo.sh', 'text/x-shellscript;charset=utf-8');
  };

  return (
    <div className="space-y-6">
      {/* Заголовок и фильтр по ролям 4 параллельных разработчиков */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">
            Архитектура GitHub-репозитория и подробное ТЗ команды (4+1 ПМИ)
          </h2>
          <p className="text-sm text-slate-600 mt-0.5">
            Скачайте полное пошаговое ТЗ для всех 4 разработчиков в формате Markdown (.md) или Word (.doc)
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() =>
              downloadFile(
                FULL_TEAM_TZ_MARKDOWN,
                'TZ_KOMANDY_RED_WINGS.md',
                'text/markdown;charset=utf-8'
              )
            }
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white rounded-lg transition-colors whitespace-nowrap shrink-0 cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Скачать ТЗ (.md)</span>
          </button>

          <button
            type="button"
            onClick={downloadTeamTzWordDoc}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-slate-900 hover:bg-slate-800 text-white rounded-lg transition-colors whitespace-nowrap shrink-0 cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Скачать ТЗ в Word (.doc)</span>
          </button>

          <button
            type="button"
            onClick={handleDownloadBootstrapScript}
            className="px-3 py-1.5 text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg transition-colors whitespace-nowrap shrink-0 cursor-pointer"
          >
            Скрипт папок (.sh)
          </button>

          <div
            className="flex flex-wrap items-center gap-1 p-1 bg-slate-100 rounded-lg border border-slate-200"
            role="group"
            aria-label="Фильтр модулей по роли разработчика"
          >
          <button
            type="button"
            onClick={() => setRoleFilter('all')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors whitespace-nowrap shrink-0 ${
              roleFilter === 'all'
                ? 'bg-slate-900 text-white'
                : 'text-slate-700 hover:text-slate-900'
            }`}
          >
            Вся команда
          </button>
          <button
            type="button"
            onClick={() => setRoleFilter('dev1_data')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors whitespace-nowrap shrink-0 ${
              roleFilter === 'dev1_data'
                ? 'bg-slate-900 text-white'
                : 'text-slate-700 hover:text-slate-900'
            }`}
          >
            Dev 1: Парсинг
          </button>
          <button
            type="button"
            onClick={() => setRoleFilter('dev2_scoring')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors whitespace-nowrap shrink-0 ${
              roleFilter === 'dev2_scoring'
                ? 'bg-slate-900 text-white'
                : 'text-slate-700 hover:text-slate-900'
            }`}
          >
            Dev 2: Скоринг
          </button>
          <button
            type="button"
            onClick={() => setRoleFilter('dev3_model')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors whitespace-nowrap shrink-0 ${
              roleFilter === 'dev3_model'
                ? 'bg-slate-900 text-white'
                : 'text-slate-700 hover:text-slate-900'
            }`}
          >
            Dev 3: Финмодель
          </button>
          <button
            type="button"
            onClick={() => setRoleFilter('dev4_ui')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors whitespace-nowrap shrink-0 ${
              roleFilter === 'dev4_ui'
                ? 'bg-slate-900 text-white'
                : 'text-slate-700 hover:text-slate-900'
            }`}
          >
            Dev 4: Streamlit UI
          </button>
          </div>
        </div>
      </div>

      {/* Матрица разделения зон ответственности 4 разработчиков */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {TEAM_WORKFLOW_ROLES.map((role) => {
          const isHighlighted = roleFilter === 'all' || roleFilter === role.id;
          return (
            <div
              key={role.id}
              onClick={() => setRoleFilter(role.id)}
              className={`p-4 rounded-xl border cursor-pointer transition-colors ${
                isHighlighted
                  ? 'bg-white border-slate-300 shadow-2xs'
                  : 'bg-slate-50 border-slate-200 opacity-65'
              }`}
            >
              <div className="flex items-center justify-between text-xs font-mono text-rose-600 font-semibold">
                <span>{role.gitBranch}</span>
              </div>
              <h3 className="text-sm font-bold text-slate-900 mt-1">{role.title}</h3>
              <p className="text-xs text-slate-600 mt-1">{role.studentRole}</p>
              <div className="mt-3 pt-2.5 border-t border-slate-200 text-xs space-y-1">
                <div className="font-mono text-slate-800">
                  Папки: {role.ownedDirectories.join(', ')}
                </div>
                <div className="text-slate-600">{role.zeroConflictRule}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Двухколоночный блок: ASCII-дерево слева + Интерактивный просмотр Python-контрактов справа */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        {/* ASCII дерево репозитория */}
        <div className="lg:col-span-5 bg-slate-900 text-slate-100 rounded-xl border border-slate-800 p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between gap-2 pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <FolderTree className="w-4 h-4 text-rose-400 shrink-0" />
                <h3 className="text-sm font-bold text-white">
                  1. Дерево репозитория (ASCII Tree)
                </h3>
              </div>
              <button
                type="button"
                onClick={() => handleCopy(ASCII_REPO_TREE, 'ascii')}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md transition-colors whitespace-nowrap shrink-0"
              >
                {copiedKey === 'ascii' ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Скопировано</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Копировать дерево</span>
                  </>
                )}
              </button>
            </div>

            <pre className="mt-3 text-xs font-mono text-slate-300 overflow-x-auto leading-relaxed">
              {ASCII_REPO_TREE}
            </pre>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-800 text-xs text-slate-400">
            Золотое правило: каждый разработчик коммитит только в свою папку внутри{' '}
            <code className="text-slate-200">src/</code>. Единственный общий файл —{' '}
            <code className="text-rose-400">src/schemas/contracts.py</code>, который замораживается в первый час работы.
          </div>
        </div>

        {/* Интерактивный инспектор кода контрактов и модулей */}
        <div className="lg:col-span-7 bg-white border border-slate-200 rounded-xl p-5 flex flex-col justify-between">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-200">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  2. Контракты API модулей и готовый шаблон кода (Python)
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Выберите файл ниже, чтобы изучить сигнатуры вызовов между app.py, скорингом и финмоделью
                </p>
              </div>

              <button
                type="button"
                onClick={() => handleCopy(activeFile.codeSnippet, activeFile.path)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-slate-900 hover:bg-slate-800 text-white rounded-lg transition-colors whitespace-nowrap shrink-0"
              >
                {copiedKey === activeFile.path ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Код скопирован</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Скопировать {activeFile.path}</span>
                  </>
                )}
              </button>
            </div>

            {/* Табы файлов */}
            <div className="flex flex-wrap gap-1.5 my-3">
              {visibleFiles.map((file) => (
                <button
                  key={file.path}
                  type="button"
                  onClick={() => setSelectedFilePath(file.path)}
                  className={`px-2.5 py-1.5 text-xs font-mono rounded-lg border transition-colors whitespace-nowrap shrink-0 ${
                    activeFile.path === file.path
                      ? 'bg-rose-600 text-white border-rose-600 font-semibold'
                      : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                  }`}
                >
                  {file.path}
                </button>
              ))}
            </div>

            {/* Метаданные выбранного файла */}
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 mb-3 text-xs flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-slate-900">
                Владелец файла: {activeFile.ownerLabel}
              </span>
              <span className="text-slate-600">{activeFile.description}</span>
            </div>

            {/* Блок исходного кода */}
            <pre className="p-4 rounded-lg bg-slate-950 text-slate-100 text-xs font-mono overflow-x-auto leading-relaxed max-h-[380px]">
              <code>{activeFile.codeSnippet}</code>
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};
