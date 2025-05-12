{ pkgs }: {
  deps = [
    pkgs.python310
    pkgs.ffmpeg
    pkgs.python310Packages.pip
    pkgs.python310Packages.pillow
    pkgs.python310Packages.flask
    pkgs.python310Packages.gunicorn
  ];
}