import os
import sys
import dulwich.porcelain as porcelain

REPO_PATH = os.path.dirname(os.path.abspath(__file__))
REMOTE_REPO = "github.com/luckyluong2k-collab/voice.git"

def main():
    print("=" * 60)
    print("  ĐẨY MÃ NGUỒN LÊN GITHUB: luckyluong2k-collab/voice")
    print("=" * 60)

    token = None
    if len(sys.argv) > 1:
        token = sys.argv[1].strip()
    else:
        token = os.environ.get("GITHUB_TOKEN", "").strip()

    if not token:
        print("\nĐể đẩy code lên GitHub repository https://github.com/luckyluong2k-collab/voice,")
        print("bạn cần cung cấp GitHub Personal Access Token (PAT).")
        print("Tạo token nhanh tại: https://github.com/settings/tokens (chọn quyền 'repo')\n")
        try:
            token = input("Nhập GitHub Token của bạn (hoặc nhấn Enter để hủy): ").strip()
        except EOFError:
            token = ""

    if not token:
        print("\n[Hủy] Chưa có token. Bạn có thể chạy lại lệnh:")
        print("  python push_to_github.py <TOKEN_CỦA_BẠN>")
        return

    push_url = f"https://{token}@{REMOTE_REPO}"

    try:
        print("\n[1/3] Đang cập nhật và commit các file mới nhất...")
        porcelain.add(REPO_PATH)
        try:
            porcelain.commit(
                REPO_PATH,
                message="Update: Added clip voice extraction, Dockerfile, Colab notebook, and documentation",
                committer="luckyluong2k <luckyluong2k@users.noreply.github.com>"
            )
            print(" -> Đã tạo commit mới!")
        except Exception as ce:
            print(f" -> Không có thay đổi mới cần commit ({ce})")

        print("\n[2/3] Đang đẩy (push) lên nhánh main trên GitHub...")
        # Push to origin
        porcelain.push(
            REPO_PATH,
            push_url,
            "refs/heads/main",
            force=True
        )
        print("\n" + "=" * 60)
        print("🎉 THÀNH CÔNG 100%!")
        print(f"Mã nguồn đã được đẩy lên: https://github.com/luckyluong2k-collab/voice")
        print("=" * 60)

    except Exception as e:
        print(f"\n[Lỗi Push] {e}")
        print("Vui lòng kiểm tra lại quyền của Token trên GitHub repository.")

if __name__ == "__main__":
    main()
