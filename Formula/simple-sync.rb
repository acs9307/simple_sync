class SimpleSync < Formula
  include Language::Python::Virtualenv

  desc "Profile-driven file synchronization tool"
  homepage "https://github.com/acs9307/simple_sync"
  url "https://github.com/acs9307/simple_sync.git",
      revision: "c22afe14dafbc611b7fe6f1c44bf03179e4e47c9"
version "0.0.4"
  license "MIT"
  head "https://github.com/acs9307/simple_sync.git", branch: "main"

  depends_on "python@3.13"

  resource "argcomplete" do
    url "https://files.pythonhosted.org/packages/source/a/argcomplete/argcomplete-3.6.3.tar.gz"
    sha256 "62e8ed4fd6a45864acc8235409461b72c9a28ee785a2011cc5eb78318786c89c"
  end

  def install
    venv = virtualenv_create(libexec, "python3.13")
    venv.pip_install resources
    venv.pip_install_and_link buildpath

    bash_output = Utils.safe_popen_read(venv.opt_bin/"register-python-argcomplete", "simple-sync")
    (bash_completion/"simple-sync").write bash_output

    zsh_output = Utils.safe_popen_read(venv.opt_bin/"register-python-argcomplete", "--shell", "zsh", "simple-sync")
    (zsh_completion/"_simple-sync").write zsh_output

    fish_output = Utils.safe_popen_read(venv.opt_bin/"register-python-argcomplete", "--shell", "fish", "simple-sync")
    (fish_completion/"simple-sync.fish").write fish_output
  end

  test do
    ENV["HOME"] = testpath.to_s
    system bin/"simple-sync", "--version"
    system bin/"simple-sync", "--config-dir", testpath/"config", "profiles"
  end
end
