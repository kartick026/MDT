import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';

/**
 * CustomSelect - Accessible, beautifully-styled dropdown replacing native <select>.
 *
 * Props:
 *   - options: Array<{ value: string|number, label: string|ReactNode, disabled?: boolean, badge?: string }>
 *   - children: <option value="...">Label</option>
 *   - value: string|number
 *   - onChange: function({ target: { value, name } }) or function(value)
 *   - placeholder: string
 *   - disabled: boolean
 *   - className: string (applied to the trigger button)
 *   - containerClassName: string (applied to the outer container)
 *   - style: object
 *   - aria-label: string
 */
export default function CustomSelect({
  value,
  onChange,
  options: propOptions,
  children,
  placeholder = 'Select…',
  disabled = false,
  className = '',
  containerClassName = '',
  style = {},
  name,
  id,
  'aria-label': ariaLabel,
  ...rest
}) {
  const generatedId = useId();
  const selectId = id || generatedId;
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const containerRef = useRef(null);
  const menuRef = useRef(null);
  const triggerRef = useRef(null);

  // Extract options from either `options` prop or `children` (<option>)
  const parsedOptions = useMemo(() => {
    if (Array.isArray(propOptions) && propOptions.length > 0) {
      return propOptions.map(opt => {
        if (typeof opt === 'string' || typeof opt === 'number') {
          return { value: String(opt), label: String(opt), disabled: false };
        }
        return {
          value: opt.value !== undefined ? String(opt.value) : '',
          label: opt.label !== undefined ? opt.label : String(opt.value),
          disabled: Boolean(opt.disabled),
          badge: opt.badge,
        };
      });
    }

    if (children) {
      const items = [];
      React.Children.forEach(children, child => {
        if (React.isValidElement(child) && child.type === 'option') {
          items.push({
            value: child.props.value !== undefined ? String(child.props.value) : '',
            label: child.props.children || String(child.props.value || ''),
            disabled: Boolean(child.props.disabled),
          });
        }
      });
      return items;
    }

    return [];
  }, [propOptions, children]);

  // Find currently selected option
  const selectedOption = useMemo(() => {
    const strVal = value !== undefined && value !== null ? String(value) : '';
    return parsedOptions.find(opt => opt.value === strVal);
  }, [parsedOptions, value]);

  // Close when clicking outside
  useEffect(() => {
    if (!isOpen) return;

    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside, true);
    document.addEventListener('touchstart', handleClickOutside, true);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside, true);
      document.removeEventListener('touchstart', handleClickOutside, true);
    };
  }, [isOpen]);

  // Sync highlighted index when opened
  useEffect(() => {
    if (isOpen) {
      const idx = parsedOptions.findIndex(o => o.value === (selectedOption?.value ?? ''));
      setHighlightedIndex(idx >= 0 ? idx : 0);
    }
  }, [isOpen, parsedOptions, selectedOption]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (isOpen && menuRef.current && highlightedIndex >= 0) {
      const items = menuRef.current.querySelectorAll('.custom-select-option');
      const item = items[highlightedIndex];
      if (item && typeof item.scrollIntoView === 'function') {
        item.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [isOpen, highlightedIndex]);

  const selectOption = useCallback((option) => {
    if (option.disabled || disabled) return;
    setIsOpen(false);

    if (typeof onChange === 'function') {
      const syntheticEvent = {
        target: { value: option.value, name: name || selectId },
        currentTarget: { value: option.value, name: name || selectId },
        preventDefault: () => {},
        stopPropagation: () => {},
      };
      onChange(syntheticEvent);
    }

    triggerRef.current?.focus();
  }, [disabled, name, onChange, selectId]);

  // Keyboard navigation
  const handleKeyDown = (e) => {
    if (disabled) return;

    switch (e.key) {
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (isOpen) {
          if (highlightedIndex >= 0 && highlightedIndex < parsedOptions.length) {
            selectOption(parsedOptions[highlightedIndex]);
          }
        } else {
          setIsOpen(true);
        }
        break;

      case 'ArrowDown':
        e.preventDefault();
        if (!isOpen) {
          setIsOpen(true);
        } else {
          setHighlightedIndex(prev => {
            let next = prev + 1;
            while (next < parsedOptions.length && parsedOptions[next].disabled) {
              next++;
            }
            return next < parsedOptions.length ? next : prev;
          });
        }
        break;

      case 'ArrowUp':
        e.preventDefault();
        if (!isOpen) {
          setIsOpen(true);
        } else {
          setHighlightedIndex(prev => {
            let next = prev - 1;
            while (next >= 0 && parsedOptions[next].disabled) {
              next--;
            }
            return next >= 0 ? next : prev;
          });
        }
        break;

      case 'Escape':
        if (isOpen) {
          e.preventDefault();
          setIsOpen(false);
          triggerRef.current?.focus();
        }
        break;

      case 'Tab':
        if (isOpen) {
          setIsOpen(false);
        }
        break;

      default:
        break;
    }
  };

  return (
    <div
      ref={containerRef}
      className={`custom-select-container ${containerClassName}`}
      style={style}
    >
      <button
        ref={triggerRef}
        id={selectId}
        type="button"
        className={`custom-select-trigger ${className} ${isOpen ? 'is-open' : ''} ${disabled ? 'is-disabled' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => !disabled && setIsOpen(prev => !prev)}
        onKeyDown={handleKeyDown}
        {...rest}
      >
        <span className="custom-select-label">
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronDown
          size={16}
          className={`custom-select-arrow ${isOpen ? 'is-rotated' : ''}`}
          aria-hidden="true"
        />
      </button>

      {/* Hidden native input for form compatibility */}
      <input
        type="hidden"
        name={name}
        value={selectedOption ? selectedOption.value : ''}
      />

      {isOpen && (
        <div
          ref={menuRef}
          className="custom-select-menu"
          role="listbox"
          aria-labelledby={selectId}
          tabIndex={-1}
        >
          {parsedOptions.length === 0 ? (
            <div className="custom-select-empty">No options available</div>
          ) : (
            parsedOptions.map((opt, index) => {
              const isSelected = selectedOption?.value === opt.value;
              const isHighlighted = highlightedIndex === index;

              return (
                <div
                  key={`${opt.value}-${index}`}
                  role="option"
                  aria-selected={isSelected}
                  aria-disabled={opt.disabled}
                  className={`custom-select-option ${isSelected ? 'is-selected' : ''} ${isHighlighted ? 'is-focused' : ''} ${opt.disabled ? 'is-disabled' : ''}`}
                  onClick={() => selectOption(opt)}
                  onMouseEnter={() => !opt.disabled && setHighlightedIndex(index)}
                >
                  <span className="custom-select-option-text">{opt.label}</span>
                  {isSelected && (
                    <Check size={14} className="custom-select-option-check" aria-hidden="true" />
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
