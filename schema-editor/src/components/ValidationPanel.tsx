import React from 'react';
import type { FormSchema } from '../types/schema';
import { validateSchema, getCompletionStats } from '../utils/validation';

interface ValidationPanelProps {
  schema: FormSchema;
}

export const ValidationPanel: React.FC<ValidationPanelProps> = ({ schema }) => {
  const errors = React.useMemo(() => validateSchema(schema), [schema]);
  const stats = React.useMemo(() => getCompletionStats(schema), [schema]);

  const errorCount = errors.filter(e => e.type === 'error').length;
  const warningCount = errors.filter(e => e.type === 'warning').length;

  return (
    <div className="h-48 border-t border-gray-200 bg-white p-4 overflow-auto custom-scrollbar">
      <h3 className="text-sm font-semibold text-gray-900 mb-3">
        Validation & Progress
      </h3>

      {/* Progress Bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs text-gray-600 mb-1">
          <span>Completion: {stats.percentage}%</span>
          <span>
            {stats.complete} complete, {stats.needsReview} need review, {stats.total} total
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-green-500 h-2 rounded-full transition-all"
            style={{ width: `${stats.percentage}%` }}
          />
        </div>
      </div>

      {/* Status Summary */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        <div className="p-3 bg-green-50 rounded-md">
          <div className="text-2xl font-bold text-green-600">{stats.complete}</div>
          <div className="text-xs text-gray-600">Complete</div>
        </div>
        <div className="p-3 bg-yellow-50 rounded-md">
          <div className="text-2xl font-bold text-yellow-600">{stats.needsReview}</div>
          <div className="text-xs text-gray-600">Needs Review</div>
        </div>
        <div className="p-3 bg-blue-50 rounded-md">
          <div className="text-2xl font-bold text-blue-600">{stats.total}</div>
          <div className="text-xs text-gray-600">Total Fields</div>
        </div>
      </div>

      {/* Errors and Warnings */}
      {errors.length > 0 && (
        <div className="space-y-2">
          <div className="flex gap-4 text-sm">
            {errorCount > 0 && (
              <span className="text-red-600 font-medium">
                {errorCount} error{errorCount !== 1 ? 's' : ''}
              </span>
            )}
            {warningCount > 0 && (
              <span className="text-yellow-600 font-medium">
                {warningCount} warning{warningCount !== 1 ? 's' : ''}
              </span>
            )}
          </div>
          <div className="max-h-32 overflow-auto custom-scrollbar space-y-1">
            {errors.map((error, idx) => (
              <div
                key={idx}
                className={`text-xs p-2 rounded ${
                  error.type === 'error'
                    ? 'bg-red-50 text-red-700'
                    : 'bg-yellow-50 text-yellow-700'
                }`}
              >
                <span className="font-mono text-xs">{error.field_id}</span>:{' '}
                {error.message}
              </div>
            ))}
          </div>
        </div>
      )}

      {errors.length === 0 && (
        <div className="text-sm text-green-600 flex items-center gap-2">
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
          No validation errors
        </div>
      )}
    </div>
  );
};
