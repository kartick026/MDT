import { useEffect, useRef } from 'react';
import { useAuth } from '../context/useAuth';
import { SignInForm } from './AuthPage';

export default function LoginModal() {
  const { loginModalOpen, closeLoginModal } = useAuth();
  const dialog = useRef(null);
  useEffect(() => {
    if (loginModalOpen && !dialog.current?.open) dialog.current?.showModal();
    if (!loginModalOpen && dialog.current?.open) dialog.current.close();
  }, [loginModalOpen]);
  return <dialog ref={dialog} className="mdt-dialog" onCancel={closeLoginModal} onClose={closeLoginModal} aria-labelledby="login-title">
    <div className="workspace-actions"><h2 id="login-title">Sign in</h2><button className="btn btn-ghost" aria-label="Close sign in" onClick={closeLoginModal}>Close</button></div>
    {loginModalOpen && <SignInForm onSuccess={closeLoginModal} />}
  </dialog>;
}
